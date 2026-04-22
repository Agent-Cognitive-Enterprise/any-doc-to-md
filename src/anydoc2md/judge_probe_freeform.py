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


def _extract_list_field(data: dict[str, object], case_id: str) -> list[object] | None:
    for key in ("issues", "findings", case_id, "issues_found", "problems", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    nested_issue = data.get("issue")
    if isinstance(nested_issue, dict):
        return [nested_issue]
    for value in data.values():
        if isinstance(value, list):
            return value
    return None


def _recover_issue_reports_from_jsonish(raw: str) -> list[FreeformIssueReport]:
    compact = raw.replace("\\n", "\n")
    pattern = re.compile(
        r'"page"\s*:\s*"(?P<page>.*?)"'
        r'.*?"candidate_excerpt"\s*:\s*"(?P<candidate_excerpt>.*?)"'
        r'.*?"why_wrong"\s*:\s*"(?P<why_wrong>.*?)"'
        r'(?:.*?"severity"\s*:\s*"(?P<severity>.*?)")?',
        flags=re.DOTALL,
    )
    reports: list[FreeformIssueReport] = []
    for match in pattern.finditer(compact):
        reports.append(
            FreeformIssueReport(
                page=match.group("page").strip(),
                candidate_excerpt=match.group("candidate_excerpt").strip(),
                why_wrong=match.group("why_wrong").strip(),
                severity=(match.group("severity") or "").strip(),
            )
        )
    return reports


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


def _build_freeform_prompt(case: FreeformProbeCase, *, source_notes: str) -> tuple[str, str]:
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
        "Compare one candidate Markdown conversion against the source notes.",
        "List only material conversion issues you can support from the evidence.",
        "If the candidate has no material issues, return an empty list.",
        "",
        "Source notes:",
        source_notes,
        "",
        f"{case.case_id} Markdown:",
        "```markdown",
        case.candidate_markdown,
        "```",
    ]
    user_lines.extend(
        [
            "",
            "Return either a JSON array of issue objects or an object shaped like:",
            '{"issues": [' + example_issue + "]}",
        ]
    )
    return system, "\n".join(user_lines)


def _parse_freeform_case_response(
    raw: str,
    *,
    case: FreeformProbeCase,
    tokens_used: int,
) -> tuple[FreeformCaseScore | None, str]:
    try:
        text = _strip_json_fences(raw)
        object_start = text.find("{")
        array_start = text.find("[")
        starts = [idx for idx in (object_start, array_start) if idx >= 0]
        if not starts:
            raise json.JSONDecodeError("No JSON array or object found", text, 0)
        data, _end = json.JSONDecoder().raw_decode(text[min(starts):])
    except json.JSONDecodeError as exc:
        reports = _recover_issue_reports_from_jsonish(raw)
        if reports:
            return _score_case(case, reports), ""
        return None, f"JSON parse error: {exc} — raw: {raw[:200]}"

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = _extract_list_field(data, case.case_id)
        if raw_items is None:
            return None, "Freeform JSON missing list field 'issues' or 'findings'"
    else:
        return None, "Freeform JSON must be an object or array"

    if not isinstance(raw_items, list):
        return None, "Freeform JSON issues/findings field must be a list"

    reports = [
        report
        for report in (_coerce_issue_report(item) for item in raw_items)
        if report is not None
    ]
    return _score_case(case, reports), ""


def run_freeform_probe(
    *,
    suite: FreeformProbeSuite,
    settings: JudgeSettings,
) -> FreeformProbeVerdict:
    case_scores: list[FreeformCaseScore] = []
    total_tokens = 0
    raw_parts: list[str] = []
    for case in suite.cases:
        system, user = _build_freeform_prompt(case, source_notes=suite.source_notes)
        try:
            raw, tokens = _call_lm_studio(system, user, settings)
        except Exception as exc:
            return FreeformProbeVerdict(
                case_scores=(),
                tokens_used=total_tokens,
                raw="\n\n".join(raw_parts),
                error=f"Judge call failed: {exc}",
            )
        total_tokens += tokens
        raw_parts.append(f"{case.case_id}:\n{raw}")
        score, error = _parse_freeform_case_response(raw, case=case, tokens_used=tokens)
        if score is None:
            return FreeformProbeVerdict(
                case_scores=tuple(case_scores),
                tokens_used=total_tokens,
                raw="\n\n".join(raw_parts),
                error=error,
            )
        case_scores.append(score)
    return FreeformProbeVerdict(
        case_scores=tuple(case_scores),
        tokens_used=total_tokens,
        raw="\n\n".join(raw_parts),
    )
