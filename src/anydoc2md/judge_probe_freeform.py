"""Freeform issue-discovery probe for phase-2 judge screening."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from anydoc2md.judge_probe_freeform_case import (
    FreeformGoldIssue,
    FreeformProbeCase,
    FreeformProbeSuite,
)
from anydoc2md.llm_judge import _call_lm_studio
from anydoc2md.settings import JudgeSettings


@dataclass(frozen=True)
class FreeformIssueReport:
    page: str
    candidate_excerpt: str
    why_wrong: str
    severity: str

    @property
    def blob(self) -> str:
        return " ".join(
            part.strip().lower()
            for part in (self.page, self.candidate_excerpt, self.why_wrong, self.severity)
            if part.strip()
        )


@dataclass(frozen=True)
class FreeformCaseScore:
    case_id: str
    matched_issue_ids: tuple[str, ...]
    false_positive_count: int
    duplicate_count: int
    min_expected_findings: int
    max_false_positives: int
    total_gold_issues: int

    @property
    def matched_count(self) -> int:
        return len(self.matched_issue_ids)

    @property
    def passed(self) -> bool:
        return (
            self.matched_count >= self.min_expected_findings
            and self.false_positive_count <= self.max_false_positives
        )


@dataclass(frozen=True)
class FreeformProbeVerdict:
    case_scores: tuple[FreeformCaseScore, ...]
    tokens_used: int
    raw: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()


def _coerce_issue_report(item: object) -> FreeformIssueReport | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return FreeformIssueReport(page="", candidate_excerpt=text, why_wrong=text, severity="")
    if not isinstance(item, dict):
        return None
    return FreeformIssueReport(
        page=str(item.get("page", "")).strip(),
        candidate_excerpt=str(item.get("candidate_excerpt", "")).strip(),
        why_wrong=str(item.get("why_wrong", "")).strip(),
        severity=str(item.get("severity", "")).strip(),
    )


def _matches_gold(issue: FreeformIssueReport, gold_issue: FreeformGoldIssue) -> bool:
    blob = issue.blob
    return all(any(term in blob for term in group) for group in gold_issue.required_term_groups)


def _score_case(
    case: FreeformProbeCase,
    issue_reports: list[FreeformIssueReport],
) -> FreeformCaseScore:
    matched_issue_ids: list[str] = []
    false_positive_count = 0
    duplicate_count = 0

    for issue in issue_reports:
        matching_ids = [
            gold_issue.issue_id
            for gold_issue in case.gold_issues
            if _matches_gold(issue, gold_issue)
        ]
        fresh_match = next(
            (issue_id for issue_id in matching_ids if issue_id not in matched_issue_ids),
            None,
        )
        if fresh_match is not None:
            matched_issue_ids.append(fresh_match)
            continue
        if matching_ids:
            duplicate_count += 1
            continue
        false_positive_count += 1

    return FreeformCaseScore(
        case_id=case.case_id,
        matched_issue_ids=tuple(matched_issue_ids),
        false_positive_count=false_positive_count,
        duplicate_count=duplicate_count,
        min_expected_findings=case.min_expected_findings,
        max_false_positives=case.max_false_positives,
        total_gold_issues=len(case.gold_issues),
    )


def _build_freeform_prompt(suite: FreeformProbeSuite) -> tuple[str, str]:
    system = (
        "You are a document conversion auditor. "
        "Discover material conversion issues from the evidence. "
        "Do not use a fixed checklist or taxonomy. "
        "Return only valid compact JSON. No markdown fences. No prose."
    )
    example_issue = (
        '{"page":"1","candidate_excerpt":"...","why_wrong":"...","severity":"medium"}'
    )
    user_lines = [
        "Compare each candidate Markdown conversion against the source notes.",
        "List only material conversion issues you can support from the evidence.",
        "If a candidate has no issues, return an empty list for that candidate.",
        "",
        "Source notes:",
        suite.source_notes,
    ]
    for case in suite.cases:
        user_lines.extend(
            [
                "",
                f"{case.case_id} Markdown:",
                "```markdown",
                case.candidate_markdown,
                "```",
            ]
        )
    cases_shape = ", ".join(f'"{case.case_id}":[{example_issue}]' for case in suite.cases)
    user_lines.extend(
        [
            "",
            "Return exactly one JSON object shaped like:",
            '{"cases": {' + cases_shape + "}}",
        ]
    )
    return system, "\n".join(user_lines)


def _parse_freeform_response(
    raw: str,
    *,
    suite: FreeformProbeSuite,
    tokens_used: int,
) -> FreeformProbeVerdict:
    try:
        text = _strip_json_fences(raw)
        json_start = text.find("{")
        if json_start < 0:
            raise json.JSONDecodeError("No JSON object found", text, 0)
        data, _end = json.JSONDecoder().raw_decode(text[json_start:])
    except json.JSONDecodeError as exc:
        return FreeformProbeVerdict(
            case_scores=(),
            tokens_used=tokens_used,
            raw=raw,
            error=f"JSON parse error: {exc} — raw: {raw[:200]}",
        )

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, dict):
        return FreeformProbeVerdict(
            case_scores=(),
            tokens_used=tokens_used,
            raw=raw,
            error="Freeform JSON missing object field 'cases'",
        )

    case_scores: list[FreeformCaseScore] = []
    for case in suite.cases:
        raw_items = raw_cases.get(case.case_id, [])
        if not isinstance(raw_items, list):
            return FreeformProbeVerdict(
                case_scores=(),
                tokens_used=tokens_used,
                raw=raw,
                error=f"Freeform JSON field cases.{case.case_id!s} must be a list",
            )
        reports = [
            report
            for report in (_coerce_issue_report(item) for item in raw_items)
            if report is not None
        ]
        case_scores.append(_score_case(case, reports))

    return FreeformProbeVerdict(case_scores=tuple(case_scores), tokens_used=tokens_used, raw=raw)


def run_freeform_probe(
    *,
    suite: FreeformProbeSuite,
    settings: JudgeSettings,
) -> FreeformProbeVerdict:
    system, user = _build_freeform_prompt(suite)
    try:
        raw, tokens = _call_lm_studio(system, user, settings)
    except Exception as exc:
        return FreeformProbeVerdict(
            case_scores=(),
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )
    return _parse_freeform_response(raw, suite=suite, tokens_used=tokens)
