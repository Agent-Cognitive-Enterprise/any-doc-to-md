"""Judge model probing runner: call the LLM judge and evaluate pass/fail."""

from __future__ import annotations

import time
from dataclasses import dataclass

from anydoc2md.judge_probe_case import (
    EXPECTED_ISSUE_CLASSES,
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

    title_keywords = (
        "title",
        "heading",
        "header",
        "fragmented",
        "split",
        "broken heading",
        "malformed heading",
    )
    bullet_keywords = (
        "bullet",
        "bullets",
        "unordered list",
        "dot list",
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
    table_keywords = (
        "table",
        "tabular",
        "rows",
        "columns",
        "cells",
        "flattened",
    )
    figure_keywords = (
        "caption",
        "figure",
        "image",
        "illustration",
        "visual",
    )

    has_title = any(keyword in combined for keyword in title_keywords)
    has_bullet_list = any(keyword in combined for keyword in bullet_keywords)
    has_numbered_list = any(keyword in combined for keyword in numbered_keywords)
    has_table = any(keyword in combined for keyword in table_keywords)
    has_figure_caption = any(keyword in combined for keyword in figure_keywords)

    if has_title:
        detected.append("title formatting")
    if has_bullet_list:
        detected.append("bullet list formatting")
    if has_numbered_list:
        detected.append("numbered list formatting")
    if has_table:
        detected.append("table fidelity")
    if has_figure_caption:
        detected.append("figure caption mismatch")
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
            reason=f"too few violations: {violations_count}",
        )
    if len(detected_issue_classes) < 4:
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
                "issue classes: " + ", ".join(detected_issue_classes or ["none"])
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
