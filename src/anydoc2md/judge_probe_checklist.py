"""Fixed-checklist LLM probe for judge model screening."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from anydoc2md.judge_probe_case import (
    CONTROL_ISSUE_IDS,
    EXPECTED_ISSUE_IDS,
    ProbeCase,
)
from anydoc2md.llm_judge import _call_lm_studio
from anydoc2md.settings import JudgeSettings

_EXPECTED_DEFINITIONS = {
    "fragmented_heading": "The title is split or malformed instead of one title.",
    "double_bullet_markers": "A list item contains duplicate bullet markers such as '- •'.",
    "malformed_dot_bullets": "Dot-style bullets are malformed, for example '.' or '..'.",
    "numbered_list_out_of_order": "A numbered procedure is not in 1, 2, 3 order.",
    "box_heading_without_content": "Box content became empty headings instead of body text.",
    "repeated_page_heading": "Running/page headings are repeated as document headings.",
    "detached_caption": "A figure caption is separated from the image it describes.",
    "wrong_caption": "A figure caption refers to the wrong step or wrong meaning.",
    "flattened_table": "A table is flattened into plain text and loses columns.",
    "implausible_image_size": "An image reference has impossible or implausible dimensions.",
    "missing_image_reference": "An image reference is broken or unresolved.",
    "image_count_mismatch": "The candidate has missing or extra image references.",
    "missing_source_text": "Material source text is omitted from the candidate.",
}

_CONTROL_DEFINITIONS = {
    "ocr_gibberish": "Large blocks of random OCR gibberish are present.",
    "wrong_language_translation": "The document was translated into the wrong language.",
    "math_formula_loss": "Mathematical formulas were lost or corrupted.",
}

_SOURCE_NOTES = """\
The source is a 10-page clinic intake packet. A faithful conversion should:
- keep the title as "Clinic Intake Checklist";
- preserve normal checklist bullets;
- keep the procedure numbered in order 1, 2, 3;
- preserve Box 1 body reminders as text, not empty headings;
- preserve the Daily Readiness table as Task / Owner / Status columns;
- keep figure captions adjacent to their images;
- describe the red square as the tray-zone marker used during Step 2;
- keep image references resolvable and sizes plausible;
- remove repeated running page headers;
- retain escalation, wet-label replacement, and chain-of-custody text.
"""


@dataclass(frozen=True)
class ChecklistProbeVerdict:
    issues: dict[str, bool]
    tokens_used: int
    raw: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error


def _candidate_markdown(probe_case: ProbeCase) -> str:
    return (probe_case.candidate.staging_dir / "index.md").read_text(encoding="utf-8")


def _build_checklist_prompt(probe_case: ProbeCase) -> tuple[str, str]:
    issue_lines = [
        f'- "{issue_id}": {_EXPECTED_DEFINITIONS[issue_id]}'
        for issue_id in EXPECTED_ISSUE_IDS
    ]
    control_lines = [
        f'- "{issue_id}": {_CONTROL_DEFINITIONS[issue_id]}' for issue_id in CONTROL_ISSUE_IDS
    ]
    all_issue_ids = EXPECTED_ISSUE_IDS + CONTROL_ISSUE_IDS
    issues_shape = ", ".join(f'"{issue_id}": false' for issue_id in all_issue_ids)
    system = (
        "You are a document conversion audit classifier. "
        "Fill a fixed checklist with boolean true/false values. "
        "Return only valid compact JSON. No markdown fences. No prose."
    )
    user = (
        "Compare the candidate Markdown against the source notes. "
        "Set an issue to true only when the candidate evidence supports it. "
        "Set negative controls to false unless that control is actually present.\n\n"
        f"Source notes:\n{_SOURCE_NOTES}\n\n"
        "Expected issue checklist:\n"
        + "\n".join(issue_lines)
        + "\n\nNegative controls:\n"
        + "\n".join(control_lines)
        + "\n\nCandidate Markdown:\n```markdown\n"
        + _candidate_markdown(probe_case)
        + "\n```\n\n"
        'Return exactly: {"issues": {'
        + issues_shape
        + "}}"
    )
    return system, user


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _parse_checklist_response(raw: str, *, tokens_used: int) -> ChecklistProbeVerdict:
    try:
        text = _strip_json_fences(raw)
        json_start = text.find("{")
        if json_start < 0:
            raise json.JSONDecodeError("No JSON object found", text, 0)
        data, _end = json.JSONDecoder().raw_decode(text[json_start:])
    except json.JSONDecodeError as exc:
        return ChecklistProbeVerdict(
            issues={},
            tokens_used=tokens_used,
            raw=raw,
            error=f"JSON parse error: {exc} — raw: {raw[:200]}",
        )

    raw_issues = data.get("issues")
    if not isinstance(raw_issues, dict):
        return ChecklistProbeVerdict(
            issues={},
            tokens_used=tokens_used,
            raw=raw,
            error="Checklist JSON missing object field 'issues'",
        )

    all_issue_ids = EXPECTED_ISSUE_IDS + CONTROL_ISSUE_IDS
    issues = {issue_id: _coerce_bool(raw_issues.get(issue_id, False)) for issue_id in all_issue_ids}
    return ChecklistProbeVerdict(issues=issues, tokens_used=tokens_used, raw=raw)


def run_checklist_probe(
    *,
    probe_case: ProbeCase,
    settings: JudgeSettings,
) -> ChecklistProbeVerdict:
    system, user = _build_checklist_prompt(probe_case)
    try:
        raw, tokens = _call_lm_studio(system, user, settings)
    except Exception as exc:
        return ChecklistProbeVerdict(
            issues={},
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )
    return _parse_checklist_response(raw, tokens_used=tokens)
