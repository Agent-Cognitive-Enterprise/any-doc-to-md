"""Issue-focused PDF judge review and aggregation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import re

from anydoc2md._llm_judge_parsing import _parse_verdict
from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md._llm_judge_prompting import _traits_summary
from anydoc2md._llm_judge_types import JudgeVerdict, JudgeViolation, JudgeWindowVerdict
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import JudgeSettings

PDF_ISSUE_REVIEW_MAX_ATTEMPTS = 3

CallLmStudio = Callable[[str, str, JudgeSettings], tuple[str, int]]


@dataclass(frozen=True)
class _IssueReviewResult:
    issue_index: int
    tokens_used: int
    window_verdict: JudgeWindowVerdict | None = None
    error: str = ""


def judge_candidate_against_source_issues(
    *,
    candidate: AdapterResult,
    traits: DocumentTraits,
    issues: list[PdfSuspectedIssue],
    settings: JudgeSettings,
    call_lm_studio: CallLmStudio,
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
            call_lm_studio=call_lm_studio,
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
    call_lm_studio: CallLmStudio,
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
                call_lm_studio=call_lm_studio,
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
                call_lm_studio=call_lm_studio,
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
    call_lm_studio: CallLmStudio,
) -> _IssueReviewResult:
    system, user = _build_issue_review_prompt(
        candidate_name=candidate.method_name,
        traits=traits,
        issue=issue,
        issue_index=issue_index,
        total_issues=total_issues,
    )

    tokens_used = 0
    failures: list[str] = []
    for attempt in range(1, PDF_ISSUE_REVIEW_MAX_ATTEMPTS + 1):
        try:
            raw, tokens = call_lm_studio(system, user, settings)
        except Exception as exc:
            failures.append(_attempt_failure(attempt, f"LM Studio call failed: {exc}"))
            continue

        tokens_used += tokens
        parsed = _parse_verdict(raw, [candidate], settings.model, tokens)
        if not parsed.succeeded:
            failures.append(_attempt_failure(attempt, parsed.error))
            continue

        return _IssueReviewResult(
            issue_index=issue_index,
            tokens_used=tokens_used,
            window_verdict=JudgeWindowVerdict(
                window_index=issue_index,
                total_windows=total_issues,
                source_page_start=issue.source_page_start,
                source_page_end=issue.source_page_end,
                candidate_page_start=issue.candidate_page_start,
                candidate_page_end=issue.candidate_page_end,
                confidence=parsed.confidence,
                reasoning=parsed.reasoning,
                tokens_used=tokens_used,
                violations=_normalize_window_pages(
                    parsed.violations,
                    source_page_start=issue.source_page_start,
                    source_page_end=issue.source_page_end,
                ),
            ),
        )

    return _IssueReviewResult(
        issue_index=issue_index,
        tokens_used=tokens_used,
        error=(
            f"Issue-focused PDF review failed in issue {issue_index}/"
            f"{total_issues} after {PDF_ISSUE_REVIEW_MAX_ATTEMPTS} attempts: "
            + "; ".join(failures)
        ),
    )


def _attempt_failure(attempt: int, message: str) -> str:
    return f"attempt {attempt}/{PDF_ISSUE_REVIEW_MAX_ATTEMPTS}: {message}"


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
