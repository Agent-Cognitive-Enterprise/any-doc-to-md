"""Core helpers for PDF judge concurrency benchmarking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import statistics
import threading
import time
from typing import Any

import fitz

from anydoc2md._llm_judge_pdf_issue_localizer import (
    PdfSuspectedIssue,
    detect_pdf_suspected_issues,
)
from anydoc2md._llm_judge_pdf_issue_reviewer import (
    judge_candidate_against_source_issues,
)
from anydoc2md._llm_judge_types import JudgeVerdict
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
import anydoc2md.llm_judge as llm_judge_module
from anydoc2md.settings import JudgeSettings


@dataclass(frozen=True)
class BenchmarkCase:
    """One source/candidate PDF pair to audit."""

    case_id: str
    source_pdf_path: Path
    audit_pdf_path: Path
    candidate_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_pdf_path": str(self.source_pdf_path),
            "audit_pdf_path": str(self.audit_pdf_path),
            "candidate_name": self.candidate_name,
        }


@dataclass(frozen=True)
class BenchmarkAttempt:
    """One concurrency-level run for one benchmark case."""

    case_id: str
    concurrency: int
    repeat_index: int
    succeeded: bool
    elapsed_s: float
    tokens_used: int
    window_count: int
    violation_count: int
    confidence: str
    max_active_calls: int
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "concurrency": self.concurrency,
            "repeat_index": self.repeat_index,
            "succeeded": self.succeeded,
            "elapsed_s": self.elapsed_s,
            "tokens_used": self.tokens_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "window_count": self.window_count,
            "violation_count": self.violation_count,
            "confidence": self.confidence,
            "max_active_calls": self.max_active_calls,
            "error": self.error,
        }


@dataclass(frozen=True)
class CaseIssueSummary:
    """Deterministic suspect-window summary for a case."""

    case_id: str
    issue_count: int
    max_source_chars: int
    max_candidate_chars: int
    max_source_pages: int
    max_candidate_pages: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "issue_count": self.issue_count,
            "max_source_chars": self.max_source_chars,
            "max_candidate_chars": self.max_candidate_chars,
            "max_source_pages": self.max_source_pages,
            "max_candidate_pages": self.max_candidate_pages,
        }


class CallTracker:
    """Thread-safe wrapper that records peak concurrent judge calls."""

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._lock = threading.Lock()
        self._active_calls = 0
        self.max_active_calls = 0

    def __call__(self, system: str, user: str, settings: JudgeSettings):
        with self._lock:
            self._active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self._active_calls)
        try:
            return self._wrapped(system, user, settings)
        finally:
            with self._lock:
                self._active_calls -= 1


def parse_case_spec(spec: str) -> BenchmarkCase:
    """Parse SOURCE::AUDIT_PDF[::CANDIDATE_NAME] into a benchmark case."""
    parts = spec.split("::")
    if len(parts) not in (2, 3):
        raise ValueError(
            "case must be SOURCE_PDF::AUDIT_PDF or SOURCE_PDF::AUDIT_PDF::CANDIDATE_NAME"
        )
    source_pdf_path = Path(parts[0]).expanduser().resolve()
    audit_pdf_path = Path(parts[1]).expanduser().resolve()
    candidate_name = parts[2].strip() if len(parts) == 3 else audit_pdf_path.parent.name
    if not candidate_name:
        raise ValueError("candidate name must not be empty")
    return BenchmarkCase(
        case_id=source_pdf_path.stem,
        source_pdf_path=source_pdf_path,
        audit_pdf_path=audit_pdf_path,
        candidate_name=candidate_name,
    )


def parse_concurrency_levels(value: str) -> list[int]:
    levels: list[int] = []
    for part in value.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            level = int(stripped)
        except ValueError as exc:
            raise ValueError(f"concurrency level must be an integer; got {stripped!r}") from exc
        if level < 1:
            raise ValueError(f"concurrency level must be positive; got {level!r}")
        levels.append(level)
    if not levels:
        raise ValueError("at least one concurrency level is required")
    return levels


def run_benchmark_matrix(
    *,
    cases: list[BenchmarkCase],
    concurrency_levels: list[int],
    repeats: int,
    base_settings: JudgeSettings,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    case_payloads: list[dict[str, Any]] = []
    attempts: list[BenchmarkAttempt] = []

    for case in cases:
        _validate_case_paths(case)
        traits = _pdf_traits(case.source_pdf_path)
        issues = detect_pdf_suspected_issues(case.source_pdf_path, case.audit_pdf_path)
        issue_summary = _summarize_issues(case.case_id, issues)
        case_payloads.append({**case.to_dict(), **issue_summary.to_dict()})
        attempts.extend(
            _run_case_attempts(
                case=case,
                traits=traits,
                issues=issues,
                concurrency_levels=concurrency_levels,
                repeats=repeats,
                base_settings=base_settings,
            )
        )

    return {
        "judge_provider": base_settings.provider,
        "judge_url": base_settings.url,
        "judge_model": base_settings.model,
        "concurrency_levels": concurrency_levels,
        "repeats": repeats,
        "cases": case_payloads,
        "attempts": [attempt.to_dict() for attempt in attempts],
        "summary": summarize_attempts(attempts),
    }


def summarize_attempts(attempts: list[BenchmarkAttempt]) -> list[dict[str, Any]]:
    by_level: dict[int, list[BenchmarkAttempt]] = {}
    for attempt in attempts:
        by_level.setdefault(attempt.concurrency, []).append(attempt)

    summaries: list[dict[str, Any]] = []
    for concurrency, level_attempts in sorted(by_level.items()):
        elapsed_values = [attempt.elapsed_s for attempt in level_attempts if attempt.succeeded]
        total_tokens = sum(attempt.tokens_used for attempt in level_attempts)
        total_input_tokens = sum(attempt.input_tokens for attempt in level_attempts)
        total_output_tokens = sum(attempt.output_tokens for attempt in level_attempts)
        summaries.append(
            {
                "concurrency": concurrency,
                "attempt_count": len(level_attempts),
                "success_count": sum(1 for attempt in level_attempts if attempt.succeeded),
                "error_count": sum(1 for attempt in level_attempts if not attempt.succeeded),
                "total_tokens_used": total_tokens,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "mean_tokens_used": round(total_tokens / len(level_attempts), 1)
                if level_attempts
                else None,
                "mean_elapsed_s": round(statistics.mean(elapsed_values), 3)
                if elapsed_values
                else None,
                "min_elapsed_s": round(min(elapsed_values), 3) if elapsed_values else None,
                "max_elapsed_s": round(max(elapsed_values), 3) if elapsed_values else None,
                "max_active_calls": max(
                    (attempt.max_active_calls for attempt in level_attempts),
                    default=0,
                ),
            }
        )
    return summaries


def _run_case_attempts(
    *,
    case: BenchmarkCase,
    traits: DocumentTraits,
    issues: list[PdfSuspectedIssue],
    concurrency_levels: list[int],
    repeats: int,
    base_settings: JudgeSettings,
) -> list[BenchmarkAttempt]:
    attempts: list[BenchmarkAttempt] = []
    for concurrency in concurrency_levels:
        settings = JudgeSettings(
            url=base_settings.url,
            model=base_settings.model,
            provider=base_settings.provider,
            api_key=base_settings.api_key,
            timeout_s=base_settings.timeout_s,
            max_tokens=base_settings.max_tokens,
            disable_thinking=base_settings.disable_thinking,
            temperature=base_settings.temperature,
            pdf_concurrency=concurrency,
            anthropic_version=base_settings.anthropic_version,
        )
        for repeat_index in range(1, repeats + 1):
            attempts.append(
                _run_attempt(
                    case=case,
                    traits=traits,
                    issues=issues,
                    settings=settings,
                    repeat_index=repeat_index,
                )
            )
    return attempts


def _run_attempt(
    *,
    case: BenchmarkCase,
    traits: DocumentTraits,
    issues: list[PdfSuspectedIssue],
    settings: JudgeSettings,
    repeat_index: int,
) -> BenchmarkAttempt:
    candidate = AdapterResult(
        method_name=case.candidate_name,
        method_version="benchmark",
        command_invoked="judge_pdf_concurrency_benchmark",
        exit_code=0,
        staging_dir=case.audit_pdf_path.parent,
        timing_ms=0,
        status="ok",
    )
    tracker = CallTracker(llm_judge_module._call_lm_studio)
    started = time.monotonic()
    verdict = judge_candidate_against_source_issues(
        candidate=candidate,
        traits=traits,
        issues=issues,
        settings=settings,
        call_lm_studio=tracker,
    )
    return _attempt_from_verdict(
        case_id=case.case_id,
        concurrency=settings.pdf_concurrency,
        repeat_index=repeat_index,
        elapsed_s=round(time.monotonic() - started, 3),
        max_active_calls=tracker.max_active_calls,
        verdict=verdict,
    )


def _attempt_from_verdict(
    *,
    case_id: str,
    concurrency: int,
    repeat_index: int,
    elapsed_s: float,
    max_active_calls: int,
    verdict: JudgeVerdict,
) -> BenchmarkAttempt:
    return BenchmarkAttempt(
        case_id=case_id,
        concurrency=concurrency,
        repeat_index=repeat_index,
        succeeded=verdict.succeeded,
        elapsed_s=elapsed_s,
        tokens_used=verdict.tokens_used,
        window_count=len(verdict.window_verdicts),
        violation_count=len(verdict.violations),
        confidence=verdict.confidence,
        max_active_calls=max_active_calls,
        error=verdict.error,
        input_tokens=verdict.input_tokens,
        output_tokens=verdict.output_tokens,
    )


def _pdf_traits(source_pdf_path: Path) -> DocumentTraits:
    with fitz.open(source_pdf_path) as doc:
        page_count = len(doc)
    return DocumentTraits(
        file_type="pdf",
        page_count=page_count,
        image_count=0,
        table_count=0,
        word_count=0,
        is_scanned=False,
        is_image_heavy=False,
        is_table_heavy=False,
        is_multi_column=False,
        is_text_only=False,
        has_math=False,
    )


def _summarize_issues(case_id: str, issues: list[PdfSuspectedIssue]) -> CaseIssueSummary:
    return CaseIssueSummary(
        case_id=case_id,
        issue_count=len(issues),
        max_source_chars=max((len(issue.source_excerpt) for issue in issues), default=0),
        max_candidate_chars=max((len(issue.candidate_excerpt) for issue in issues), default=0),
        max_source_pages=max(
            (issue.source_page_end - issue.source_page_start + 1 for issue in issues),
            default=0,
        ),
        max_candidate_pages=max(
            (issue.candidate_page_end - issue.candidate_page_start + 1 for issue in issues),
            default=0,
        ),
    )


def _validate_case_paths(case: BenchmarkCase) -> None:
    if not case.source_pdf_path.is_file():
        raise FileNotFoundError(f"source PDF not found: {case.source_pdf_path}")
    if not case.audit_pdf_path.is_file():
        raise FileNotFoundError(f"audit PDF not found: {case.audit_pdf_path}")
