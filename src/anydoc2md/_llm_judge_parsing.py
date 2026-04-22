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

    text = _normalize_json_candidate(raw)

    data, error = _try_parse_json(text)
    if data is None:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=model,
            tokens_used=tokens,
            error=f"JSON parse error: {error} — raw: {raw[:200]}",
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


def _try_parse_json(text: str) -> tuple[dict | None, str]:
    data, error = _decode_json_object(text)
    if data is not None:
        return data, ""

    candidate = _extract_json_candidate(text)
    if not candidate:
        return None, error

    data, candidate_error = _decode_json_object(candidate)
    if data is not None:
        return data, ""

    repaired = _repair_json_candidate(candidate)
    if repaired != candidate:
        data, repaired_error = _decode_json_object(repaired)
        if data is not None:
            return data, ""
        return None, repaired_error

    return None, candidate_error


def _decode_json_object(text: str) -> tuple[dict | None, str]:
    stripped = text.lstrip()
    if not stripped:
        return None, "empty JSON response"
    try:
        data, _end = json.JSONDecoder().raw_decode(stripped)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if isinstance(data, dict):
        return data, ""
    return None, f"expected JSON object, got {type(data).__name__}"


def _extract_json_candidate(text: str) -> str:
    first = text.find("{")
    if first < 0:
        return ""
    last = text.rfind("}")
    if last > first:
        return text[first:last + 1]
    return text[first:]


def _repair_json_candidate(text: str) -> str:
    repaired: list[str] = []
    closers: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                repaired.append(char)
                escaped = False
                continue
            if char == "\\":
                repaired.append(char)
                escaped = True
                continue
            if char == '"':
                repaired.append(char)
                in_string = False
                continue
            if char == "\n":
                repaired.append("\\n")
                continue
            if char == "\r":
                repaired.append("\\r")
                continue
            if char == "\t":
                repaired.append("\\t")
                continue
            if ord(char) < 32:
                repaired.append(" ")
                continue
            repaired.append(char)
            continue

        if char == '"':
            repaired.append(char)
            in_string = True
            continue
        if char == "{":
            repaired.append(char)
            closers.append("}")
            continue
        if char == "[":
            repaired.append(char)
            closers.append("]")
            continue
        if char in {"}", "]"}:
            if closers and char == closers[-1]:
                closers.pop()
                repaired.append(char)
            continue
        repaired.append(char)

    if in_string:
        repaired.append('"')
    while closers:
        repaired.append(closers.pop())

    compact = "".join(repaired)
    compact = re.sub(r",(\s*[}\]])", r"\1", compact)
    return _sanitize_control_characters(compact)


def _normalize_json_candidate(raw: str) -> str:
    # Strip markdown code fences if present.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return text.strip()


def _sanitize_control_characters(text: str) -> str:
    return "".join(
        ch if (ord(ch) >= 32 or ch in "\n\r\t") else " "
        for ch in text
    )
