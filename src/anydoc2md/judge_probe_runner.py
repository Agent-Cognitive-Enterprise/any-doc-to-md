"""Judge model probing runner: call the LLM judge and evaluate pass/fail."""

from __future__ import annotations

import time
from dataclasses import dataclass

from anydoc2md.judge_probe_case import (
    EXPECTED_ISSUE_CLASSES,
    MIN_REQUIRED_ISSUE_CLASSES,
    ProbeCase,
)
from anydoc2md.judge_probe_models import ModelInfo
from anydoc2md.llm_judge import judge_candidate_against_source
from anydoc2md.settings import JudgeSettings


@dataclass(frozen=True)
class ProbeResult:
    model_id: str
    size_hint_b: float | None
    latency_s: float
    tokens_used: int
    confidence: str
    violations_count: int
    passed: bool
    reason: str


def _collect_verdict_text(verdict) -> str:
    parts: list[str] = []
    parts.append(getattr(verdict, "reasoning", "") or "")
    parts.append(getattr(verdict, "uncertainty_note", "") or "")
    notes = getattr(verdict, "notes", {}) or {}
    if isinstance(notes, dict):
        parts.extend(str(value) for value in notes.values())
    violations = getattr(verdict, "violations", []) or []
    for violation in violations:
        parts.append(getattr(violation, "type", "") or "")
        parts.append(getattr(violation, "evidence", "") or "")
        parts.append(getattr(violation, "root_cause", "") or "")
    return " ".join(part for part in parts if part).lower()


def _detect_issue_classes(combined: str) -> list[str]:
    detected: list[str] = []

    fragmented_heading_keywords = (
        "fragmented heading",
        "heading fragmentation",
        "title",
        "heading",
        "header",
        "fragmented",
        "split",
        "broken heading",
        "malformed heading",
    )
    double_bullet_keywords = (
        "double bullet",
        "double bullets",
        "two bullet",
        "duplicate bullet",
    )
    dot_bullet_keywords = (
        "dot bullet",
        "dot bullets",
        "malformed bullet",
        "malformed bullets",
        "bullet",
        "bullets",
        "unordered list",
        "list marker",
        "list markers",
    )
    numbered_keywords = (
        "numbered",
        "numbering",
        "numeric list",
        "ordered list",
        "reading_order",
        "reading order",
        "out of order",
        "sequence",
        "step order",
        "step sequence",
        "reordered",
        "swapped",
    )
    box_keywords = (
        "box heading",
        "box title",
        "box",
        "empty heading",
        "no content",
        "without content",
    )
    repeated_heading_keywords = (
        "repeated heading",
        "repeated header",
        "page header",
        "running header",
        "duplicate heading",
    )
    detached_caption_keywords = (
        "detached caption",
        "caption detached",
        "caption not adjacent",
        "caption separated",
        "image moved",
        "image at the end",
    )
    wrong_caption_keywords = (
        "wrong caption",
        "caption mismatch",
        "incorrect caption",
        "points to the wrong step",
        "step 3",
    )
    table_keywords = (
        "table",
        "tabular",
        "rows",
        "columns",
        "cells",
        "flattened",
    )
    image_size_keywords = (
        "image size",
        "image width",
        "implausible",
        "suspiciously large",
        "zero width",
        "missing width",
    )
    missing_image_keywords = (
        "missing image",
        "missing image reference",
        "image reference",
        "unresolved image",
        "broken image",
    )
    image_count_keywords = (
        "image count",
        "extra image",
        "too many images",
        "image mismatch",
    )
    text_coverage_keywords = (
        "text coverage",
        "missing source text",
        "missing text",
        "omitted text",
        "text omitted",
    )

    has_fragmented_heading = any(keyword in combined for keyword in fragmented_heading_keywords)
    has_double_bullet = any(keyword in combined for keyword in double_bullet_keywords)
    has_dot_bullet = any(keyword in combined for keyword in dot_bullet_keywords)
    has_numbered_list = any(keyword in combined for keyword in numbered_keywords)
    has_box = any(keyword in combined for keyword in box_keywords)
    has_repeated_heading = any(keyword in combined for keyword in repeated_heading_keywords)
    has_detached_caption = any(keyword in combined for keyword in detached_caption_keywords)
    has_wrong_caption = any(keyword in combined for keyword in wrong_caption_keywords)
    has_table = any(keyword in combined for keyword in table_keywords)
    has_image_size = any(keyword in combined for keyword in image_size_keywords)
    has_missing_image = any(keyword in combined for keyword in missing_image_keywords)
    has_image_count = any(keyword in combined for keyword in image_count_keywords)
    has_text_coverage = any(keyword in combined for keyword in text_coverage_keywords)

    if has_fragmented_heading:
        detected.append("fragmented heading")
    if has_double_bullet:
        detected.append("double bullet markers")
    if has_dot_bullet:
        detected.append("malformed dot bullet list")
    if has_numbered_list:
        detected.append("numbered list sequencing")
    if has_box:
        detected.append("box heading without content")
    if has_repeated_heading:
        detected.append("repeated page heading")
    if has_detached_caption:
        detected.append("detached figure caption")
    if has_wrong_caption:
        detected.append("wrong figure caption")
    if has_table:
        detected.append("flattened table")
    if has_image_size:
        detected.append("implausible image size")
    if has_missing_image:
        detected.append("missing image reference")
    if has_image_count:
        detected.append("image count mismatch")
    if has_text_coverage:
        detected.append("missing source text")
    return detected


def probe_one_model(
    *,
    model: ModelInfo,
    judge_url: str,
    judge_timeout_s: int,
    probe_case: ProbeCase,
) -> ProbeResult:
    settings = JudgeSettings(
        url=judge_url,
        model=model.model_id,
        timeout_s=judge_timeout_s,
    )
    t0 = time.perf_counter()
    verdict = judge_candidate_against_source(
        probe_case.candidate,
        probe_case.source_pdf,
        probe_case.traits,
        audit_pdf_path=probe_case.candidate_pdf,
        settings=settings,
    )
    latency_s = max(0.0, time.perf_counter() - t0)

    tokens_used = getattr(verdict, "tokens_used", 0) or 0
    confidence = getattr(verdict, "confidence", "error") or "error"
    violations = getattr(verdict, "violations", []) or []
    violations_count = len(violations) if isinstance(violations, list) else 0
    error = getattr(verdict, "error", "") or ""

    combined = _collect_verdict_text(verdict)
    detected_issue_classes = _detect_issue_classes(combined)
    missing_issue_classes = [
        issue_class for issue_class in EXPECTED_ISSUE_CLASSES
        if issue_class not in detected_issue_classes
    ]

    if confidence == "error":
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            confidence=confidence,
            violations_count=violations_count,
            passed=False,
            reason=error or "judge returned confidence=error",
        )
    if violations_count < 2:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            confidence=confidence,
            violations_count=violations_count,
            passed=False,
            reason=(
                f"low detection rate: {violations_count} violations reported; "
                "need at least 2"
            ),
        )
    if len(detected_issue_classes) < MIN_REQUIRED_ISSUE_CLASSES:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            confidence=confidence,
            violations_count=violations_count,
            passed=False,
            reason=(
                f"surfaced {len(detected_issue_classes)}/{len(EXPECTED_ISSUE_CLASSES)} "
                f"issue classes; need at least {MIN_REQUIRED_ISSUE_CLASSES}: "
                + ", ".join(detected_issue_classes or ["none"])
            ),
        )

    return ProbeResult(
        model_id=model.model_id,
        size_hint_b=model.size_hint_b,
        latency_s=latency_s,
        tokens_used=tokens_used,
        confidence=confidence,
        violations_count=violations_count,
        passed=True,
        reason=(
            "ok"
            if not missing_issue_classes
            else "missing one issue class but audit was otherwise strong: " + ", ".join(missing_issue_classes)
        ),
    )
