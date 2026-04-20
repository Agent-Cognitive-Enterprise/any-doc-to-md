"""Response parsing helpers for the LLM judge."""

from __future__ import annotations

import json
import re

from anydoc2md._llm_judge_types import JudgeVerdict, JudgeViolation
from anydoc2md.format_converters.adapters.base import AdapterResult


def _parse_violations(raw_violations: object) -> list[JudgeViolation]:
    if not isinstance(raw_violations, list):
        return []

    violations: list[JudgeViolation] = []
    for item in raw_violations:
        if not isinstance(item, dict):
            continue
        raw_pages = item.get("pages", [])
        pages = [int(page) for page in raw_pages if isinstance(page, (int, float))]
        raw_confidence = item.get("confidence", 0.0)
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.0
        raw_count = item.get("count", 1)
        count = int(raw_count) if isinstance(raw_count, (int, float)) else 1
        violations.append(
            JudgeViolation(
                type=str(item.get("type", "unknown")),
                severity=str(item.get("severity", "major")),
                count=max(1, count),
                pages=pages,
                confidence=confidence,
                evidence=str(item.get("evidence", "")),
                root_cause=str(item.get("root_cause", "")),
            )
        )
    return violations


def _parse_verdict(
    raw: str,
    candidates: list[AdapterResult],
    model: str,
    tokens: int,
) -> JudgeVerdict:
    """
    Parse the LLM JSON response into a JudgeVerdict.

    Falls back to confidence="error" if the JSON is malformed or the
    preferred adapter name doesn't match any candidate.
    """
    valid_names = {r.method_name for r in candidates}

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=model,
            tokens_used=tokens,
            error=f"JSON parse error: {exc} — raw: {raw[:200]}",
        )

    preferred = data.get("preferred", "")
    if preferred not in valid_names:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=model,
            tokens_used=tokens,
            error=(
                f"LLM returned unknown adapter {preferred!r}; expected one of {sorted(valid_names)}"
            ),
        )

    confidence = data.get("confidence", "medium")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    overall_confidence = data.get("overall_confidence")
    if not isinstance(overall_confidence, (int, float)):
        overall_confidence = None

    notes = data.get("notes", {})
    if not isinstance(notes, dict):
        notes = {}

    return JudgeVerdict(
        preferred_adapter=preferred,
        confidence=confidence,
        reasoning=data.get("reasoning", ""),
        notes=notes,
        model_used=model,
        tokens_used=tokens,
        violations=_parse_violations(data.get("violations", [])),
        overall_confidence=float(overall_confidence) if overall_confidence is not None else None,
        uncertainty_note=str(data.get("uncertainty_note", "")),
        error="",
    )

