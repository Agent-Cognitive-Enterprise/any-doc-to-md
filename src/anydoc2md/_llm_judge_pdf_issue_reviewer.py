"""Issue-focused PDF judge review and aggregation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

from anydoc2md._llm_judge_parsing import _parse_verdict
from anydoc2md._llm_judge_pdf_issue_aggregation import (
    aggregate_windowed_verdict,
    normalize_window_pages,
)
from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md._llm_judge_prompting import _traits_summary
from anydoc2md._llm_judge_rate_limit import rate_limit_retry_delay_s
from anydoc2md._llm_judge_types import (
    JudgeCallResult,
    JudgeVerdict,
    JudgeWindowVerdict,
    coerce_judge_call_result,
)
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import JudgeSettings

PDF_ISSUE_REVIEW_MAX_ATTEMPTS = 3

CallLmStudio = Callable[[str, str, JudgeSettings], JudgeCallResult | tuple[str, int]]


@dataclass(frozen=True)
class _IssueReviewResult:
    issue_index: int
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
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
    total_input_tokens = 0
    total_output_tokens = 0
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
        total_input_tokens += sum(result.input_tokens for result in batch_results)
        total_output_tokens += sum(result.output_tokens for result in batch_results)
        for result in batch_results:
            if result.error:
                return JudgeVerdict(
                    preferred_adapter="",
                    confidence="error",
                    reasoning="",
                    notes={},
                    model_used=settings.model,
                    tokens_used=total_tokens,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    window_verdicts=window_verdicts,
                    error=result.error,
                )
            if result.window_verdict is not None:
                window_verdicts.append(result.window_verdict)

    return aggregate_windowed_verdict(
        candidate_name=candidate.method_name,
        model_used=settings.model,
        tokens_used=total_tokens,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
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
    input_tokens = 0
    output_tokens = 0
    failures: list[str] = []
    for attempt in range(1, PDF_ISSUE_REVIEW_MAX_ATTEMPTS + 1):
        try:
            call_result = coerce_judge_call_result(
                call_lm_studio(system, user, settings)
            )
        except Exception as exc:
            failures.append(_attempt_failure(attempt, f"Judge call failed: {exc}"))
            delay_s = rate_limit_retry_delay_s(exc, attempt=attempt, settings=settings)
            if delay_s > 0 and attempt < PDF_ISSUE_REVIEW_MAX_ATTEMPTS:
                time.sleep(delay_s)
            continue

        tokens_used += call_result.tokens_used
        input_tokens += call_result.input_tokens
        output_tokens += call_result.output_tokens
        parsed = _parse_verdict(
            call_result.text,
            [candidate],
            settings.model,
            call_result.tokens_used,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
        )
        if not parsed.succeeded:
            failures.append(_attempt_failure(attempt, parsed.error))
            continue

        return _IssueReviewResult(
            issue_index=issue_index,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                violations=normalize_window_pages(
                    parsed.violations,
                    source_page_start=issue.source_page_start,
                    source_page_end=issue.source_page_end,
                ),
            ),
        )

    return _IssueReviewResult(
        issue_index=issue_index,
        tokens_used=tokens_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=(
            f"Issue-focused PDF review failed in issue {issue_index}/"
            f"{total_issues} after {PDF_ISSUE_REVIEW_MAX_ATTEMPTS} attempts: "
            + "; ".join(failures)
        ),
    )


def _attempt_failure(attempt: int, message: str) -> str:
    return f"attempt {attempt}/{PDF_ISSUE_REVIEW_MAX_ATTEMPTS}: {message}"


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
