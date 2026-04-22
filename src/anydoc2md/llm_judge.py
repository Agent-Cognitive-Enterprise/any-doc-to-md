"""
LLM judge — audit candidate outputs and break ties when needed.

This module supports two related tasks:
- auditing a selected candidate against source context
- breaking ties between multiple near-tied candidates

Fallback behavior: when the LLM call fails (network, timeout, bad JSON), the
returned verdict has confidence="error" and an error message. Callers should
fall back to score-based selection.

Usage:
    from anydoc2md.llm_judge import judge_candidate_against_source
    from anydoc2md.settings import JudgeSettings

    settings = JudgeSettings(
        url="http://127.0.0.1:1234/v1",
        model="qwen/qwen3.6-35b-a3b",
    )

    verdict = judge_candidate_against_source(
        candidate,
        source_path,
        traits,
        audit_pdf_path=candidate.staging_dir / "audit_candidate.pdf",
        settings=settings,
    )
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import re

import requests

from anydoc2md._llm_judge_parsing import _parse_verdict, _parse_violations
from anydoc2md._llm_judge_pdf_issue_localizer import (
    PdfSuspectedIssue,
    detect_pdf_suspected_issues,
)
from anydoc2md._llm_judge_prompting import (
    EXCERPT_CHARS_PER_ADAPTER,
    _evidence_block,
    _excerpt,
    _traits_summary,
    build_audit_prompt,
    build_prompt,
)
from anydoc2md._llm_judge_types import JudgeVerdict, JudgeViolation, JudgeWindowVerdict
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
)


@dataclass(frozen=True)
class _IssueReviewResult:
    issue_index: int
    tokens_used: int
    window_verdict: JudgeWindowVerdict | None = None
    error: str = ""


def _call_lm_studio(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> tuple[str, int]:
    """
    Send a chat completion request to an OpenAI-compatible endpoint.

    Returns (response_text, tokens_used).
    Raises on network failure.
    """
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        # chat_template_kwargs disables thinking mode on Qwen3 models,
        # ensuring the JSON response lands in content (not reasoning_content).
        "chat_template_kwargs": {"thinking": False} if settings.disable_thinking else {},
    }

    resp = requests.post(
        f"{settings.url.rstrip('/')}/chat/completions",
        json=payload,
        timeout=settings.timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


def judge_near_tie(
    candidates: list[AdapterResult],
    source_path: Path,
    traits: DocumentTraits,
    *,
    settings: JudgeSettings | None = None,
) -> JudgeVerdict:
    """
    Ask the LLM judge to select the best conversion among near-tied adapters.

    Returns:
        JudgeVerdict. On network/parse failure, confidence=="error" and
        preferred_adapter=="" — caller should fall back to score-based winner.
    """
    if len(candidates) < 2:
        name = candidates[0].method_name if candidates else ""
        return JudgeVerdict(
            preferred_adapter=name,
            confidence="high",
            reasoning="Only one candidate — no judging needed.",
            notes={},
            model_used="",
            tokens_used=0,
        )

    try:
        judge_settings = settings or load_judge_settings_from_env()
    except AnyDocToMdConfigError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="",
            tokens_used=0,
            error=str(exc),
        )

    system, user = build_prompt(candidates, traits)

    try:
        raw, tokens = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )

    return _parse_verdict(raw, candidates, judge_settings.model, tokens)


def judge_candidate_against_source(
    candidate: AdapterResult,
    source_path: Path,
    traits: DocumentTraits,
    *,
    audit_pdf_path: Path,
    settings: JudgeSettings | None = None,
) -> JudgeVerdict:
    """Audit one selected candidate against source context."""
    try:
        judge_settings = settings or load_judge_settings_from_env()
    except AnyDocToMdConfigError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="",
            tokens_used=0,
            error=str(exc),
        )

    if source_path.suffix.lower() == ".pdf" and audit_pdf_path.suffix.lower() == ".pdf":
        try:
            issues = detect_pdf_suspected_issues(source_path, audit_pdf_path)
        except Exception:
            issues = None
        if issues == []:
            return JudgeVerdict(
                preferred_adapter=candidate.method_name,
                confidence="high",
                reasoning=(
                    "Deterministic source/candidate PDF checks found no suspicious "
                    "windows that required LLM review."
                ),
                notes={candidate.method_name: "No deterministic PDF issues detected."},
                model_used="",
                tokens_used=0,
                violations=[],
                window_verdicts=[],
                overall_confidence=0.95,
                uncertainty_note="PDF audit short-circuited: no deterministic suspect windows.",
                error="",
            )
        if issues:
            return _judge_candidate_against_source_issues(
                candidate=candidate,
                traits=traits,
                issues=issues,
                settings=judge_settings,
            )

    system, user = build_audit_prompt(candidate, source_path, traits, audit_pdf_path)
    try:
        raw, tokens = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )
    return _parse_verdict(raw, [candidate], judge_settings.model, tokens)


def _judge_candidate_against_source_issues(
    *,
    candidate: AdapterResult,
    traits: DocumentTraits,
    issues: list[PdfSuspectedIssue],
    settings: JudgeSettings,
) -> JudgeVerdict:
    window_verdicts: list[JudgeWindowVerdict] = []
    total_tokens = 0
    concurrency = min(max(1, settings.pdf_concurrency), len(issues))

    for batch_start in range(0, len(issues), concurrency):
        batch = list(
            enumerate(
                issues[batch_start:batch_start + concurrency],
                start=batch_start + 1,
            )
        )
        batch_results = _review_pdf_issue_batch(
            candidate=candidate,
            traits=traits,
            issues=batch,
            total_issues=len(issues),
            settings=settings,
            max_workers=concurrency,
        )
        total_tokens += sum(result.tokens_used for result in batch_results)
        for result in batch_results:
            if result.error:
                return JudgeVerdict(
                    preferred_adapter="",
                    confidence="error",
                    reasoning="",
                    notes={},
                    model_used=settings.model,
                    tokens_used=total_tokens,
                    window_verdicts=window_verdicts,
                    error=result.error,
                )
            if result.window_verdict is not None:
                window_verdicts.append(result.window_verdict)

    return _aggregate_windowed_verdict(
        candidate_name=candidate.method_name,
        model_used=settings.model,
        tokens_used=total_tokens,
        window_verdicts=window_verdicts,
    )


def _review_pdf_issue_batch(
    *,
    candidate: AdapterResult,
    traits: DocumentTraits,
    issues: list[tuple[int, PdfSuspectedIssue]],
    total_issues: int,
    settings: JudgeSettings,
    max_workers: int,
) -> list[_IssueReviewResult]:
    if max_workers <= 1 or len(issues) <= 1:
        return [
            _review_pdf_issue(
                candidate=candidate,
                traits=traits,
                issue=issue,
                issue_index=issue_index,
                total_issues=total_issues,
                settings=settings,
            )
            for issue_index, issue in issues
        ]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _review_pdf_issue,
                candidate=candidate,
                traits=traits,
                issue=issue,
                issue_index=issue_index,
                total_issues=total_issues,
                settings=settings,
            )
            for issue_index, issue in issues
        ]
        return [future.result() for future in futures]


def _review_pdf_issue(
    *,
    candidate: AdapterResult,
    traits: DocumentTraits,
    issue: PdfSuspectedIssue,
    issue_index: int,
    total_issues: int,
    settings: JudgeSettings,
) -> _IssueReviewResult:
    system, user = _build_issue_review_prompt(
        candidate_name=candidate.method_name,
        traits=traits,
        issue=issue,
        issue_index=issue_index,
        total_issues=total_issues,
    )
    try:
        raw, tokens = _call_lm_studio(system, user, settings)
    except Exception as exc:
        return _IssueReviewResult(
            issue_index=issue_index,
            tokens_used=0,
            error=(
                "LM Studio call failed during issue-focused PDF review "
                f"({issue_index}/{total_issues}): {exc}"
            ),
        )

    parsed = _parse_verdict(raw, [candidate], settings.model, tokens)
    if not parsed.succeeded:
        return _IssueReviewResult(
            issue_index=issue_index,
            tokens_used=tokens,
            error=(
                f"Issue-focused PDF review failed in issue {issue_index}/"
                f"{total_issues}: {parsed.error}"
            ),
        )

    return _IssueReviewResult(
        issue_index=issue_index,
        tokens_used=tokens,
        window_verdict=JudgeWindowVerdict(
            window_index=issue_index,
            total_windows=total_issues,
            source_page_start=issue.source_page_start,
            source_page_end=issue.source_page_end,
            candidate_page_start=issue.candidate_page_start,
            candidate_page_end=issue.candidate_page_end,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            tokens_used=tokens,
            violations=_normalize_window_pages(
                parsed.violations,
                source_page_start=issue.source_page_start,
                source_page_end=issue.source_page_end,
            ),
        ),
    )


def _aggregate_windowed_verdict(
    *,
    candidate_name: str,
    model_used: str,
    tokens_used: int,
    window_verdicts: list[JudgeWindowVerdict],
) -> JudgeVerdict:
    merged_violations = _merge_window_violations(window_verdicts)
    confidence = _aggregate_confidence([window.confidence for window in window_verdicts])
    return JudgeVerdict(
        preferred_adapter=candidate_name,
        confidence=confidence,
        reasoning=(
            f"Issue-focused PDF review across {len(window_verdicts)} suspect window(s); "
            f"{len(merged_violations)} aggregated material violation(s)."
        ),
        notes={
            candidate_name: (
                f"Issue-focused PDF review across {len(window_verdicts)} suspect window(s)."
            )
        },
        model_used=model_used,
        tokens_used=tokens_used,
        violations=merged_violations,
        window_verdicts=window_verdicts,
        overall_confidence=_confidence_score(confidence),
        uncertainty_note=(
            "Violations aggregated from deterministic suspect windows and narrow issue review."
        ),
        error="",
    )


def _build_issue_review_prompt(
    *,
    candidate_name: str,
    traits: DocumentTraits,
    issue: PdfSuspectedIssue,
    issue_index: int,
    total_issues: int,
) -> tuple[str, str]:
    system = (
        "You are an expert document-conversion quality evaluator. "
        "A deterministic checker already localized one suspected PDF issue. "
        "Your job is to review only that suspected issue, not to audit the whole document.\n\n"
        "Rules:\n"
        "- Do not invent additional issue classes outside the provided suspect.\n"
        "- Do not treat harmless reflow, line wrapping, or different page counts as problems.\n"
        "- Confirm the issue only if the supplied source and candidate excerpts show a real semantic mismatch.\n"
        "- If the deterministic suspicion is a false alarm, return an empty violations list.\n"
        "- Keep reasoning to at most 2 short sentences.\n"
        "- Return at most 2 violations, and prefer 1 when a single violation explains the issue.\n"
        "- Keep notes, evidence, and root_cause terse, with no line breaks inside JSON strings.\n\n"
        "Return ONLY compact valid JSON with this exact shape:\n"
        "{\n"
        '  "preferred": "<candidate_name>",\n'
        '  "confidence": "high|medium|low",\n'
        '  "reasoning": "<max 2 short sentences>",\n'
        '  "notes": {"<candidate_name>": "<brief note, max 12 words>"},\n'
        '  "violations": [\n'
        "    {\n"
        '      "type": "<violation_type>",\n'
        '      "severity": "critical|major|minor",\n'
        '      "count": 1,\n'
        '      "pages": [12, 13],\n'
        '      "confidence": 0.0,\n'
        '      "evidence": "<short evidence, max 25 words>",\n'
        '      "root_cause": "<likely root cause, max 12 words>"\n'
        "    }\n"
        "  ],\n"
        '  "overall_confidence": 0.0,\n'
        '  "uncertainty_note": "<optional uncertainty note>"\n'
        "}"
    )
    user = (
        "## Source document\n"
        f"{_traits_summary(traits)}\n\n"
        f"## Suspected issue {issue_index}/{total_issues}\n"
        f"Type: {issue.issue_type}\n"
        f"Description: {issue.description}\n"
        f"Source pages: {issue.source_page_start}-{issue.source_page_end}\n"
        f"Candidate pages: {issue.candidate_page_start}-{issue.candidate_page_end}\n\n"
        "## Source PDF excerpt\n\n"
        f"```text\n{issue.source_excerpt}\n```\n\n"
        "## Candidate PDF excerpt\n\n"
        f"```text\n{issue.candidate_excerpt}\n```\n\n"
        "## Task\n"
        "Review only this suspected issue. If it is real, return the smallest set of "
        "material violations needed to explain it. If the deterministic checker was too "
        "strict and the source meaning is preserved, return no violations. "
        f'Set "preferred" to exactly "{candidate_name}".'
    )
    return system, user


def _merge_window_violations(window_verdicts: list[JudgeWindowVerdict]) -> list[JudgeViolation]:
    merged: dict[tuple[str, str, str, str], JudgeViolation] = {}
    ordered_keys: list[tuple[str, str, str, str]] = []
    for window in window_verdicts:
        for violation in window.violations:
            key = (
                violation.type,
                violation.severity,
                _normalize_merge_text(violation.root_cause),
                _normalize_merge_text(violation.evidence),
            )
            if key not in merged:
                merged[key] = JudgeViolation(
                    type=violation.type,
                    severity=violation.severity,
                    count=max(1, violation.count),
                    pages=sorted(set(violation.pages)),
                    confidence=violation.confidence,
                    evidence=violation.evidence,
                    root_cause=violation.root_cause,
                )
                ordered_keys.append(key)
                continue

            existing = merged[key]
            merged[key] = JudgeViolation(
                type=existing.type,
                severity=existing.severity,
                count=existing.count + max(1, violation.count),
                pages=sorted(set(existing.pages + violation.pages)),
                confidence=max(existing.confidence, violation.confidence),
                evidence=existing.evidence,
                root_cause=existing.root_cause,
            )
    return [merged[key] for key in ordered_keys]


def _normalize_window_pages(
    violations: list[JudgeViolation],
    *,
    source_page_start: int,
    source_page_end: int,
) -> list[JudgeViolation]:
    normalized: list[JudgeViolation] = []
    for violation in violations:
        pages = [
            page
            for page in violation.pages
            if source_page_start <= page <= source_page_end
        ]
        if not pages:
            pages = [source_page_start]
        normalized.append(
            JudgeViolation(
                type=violation.type,
                severity=violation.severity,
                count=violation.count,
                pages=sorted(set(pages)),
                confidence=violation.confidence,
                evidence=violation.evidence,
                root_cause=violation.root_cause,
            )
        )
    return normalized


def _aggregate_confidence(confidences: list[str]) -> str:
    if not confidences:
        return "medium"
    order = {"low": 0, "medium": 1, "high": 2}
    return min(confidences, key=lambda value: order.get(value, 1))


def _confidence_score(confidence: str) -> float | None:
    scores = {"low": 0.45, "medium": 0.7, "high": 0.9}
    return scores.get(confidence)


def _normalize_merge_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
