"""Judge model probing runner: call the LLM judge and evaluate pass/fail."""

from __future__ import annotations

import time
from dataclasses import dataclass

from anydoc2md.judge_probe_case import (
    FIGURE_MARKER,
    INTRO_MARKER,
    STEP_ONE_MARKER,
    STEP_TWO_MARKER,
    REQUIRED_MARKERS,
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
    missing_markers = [m for m in REQUIRED_MARKERS if m.lower() not in combined]

    order_keywords = ("reading order", "out of order", "sequence", "step order")
    image_keywords = ("figure", "caption", "image")

    has_order_issue = (
        STEP_ONE_MARKER.lower() in combined
        and STEP_TWO_MARKER.lower() in combined
        and any(keyword in combined for keyword in order_keywords)
    )
    has_timing_issue = (
        INTRO_MARKER.lower() in combined
        and (
            ("before" in combined and "after" in combined)
            or "instead of" in combined
            or "timing" in combined
            or "reversed" in combined
        )
    )
    has_figure_issue = (
        FIGURE_MARKER.lower() in combined
        and any(keyword in combined for keyword in image_keywords)
    )

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
    if missing_markers:
        missing = ", ".join(missing_markers)
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            confidence=confidence,
            violations_count=violations_count,
            passed=False,
            reason=f"missing markers in response: {missing}",
        )

    missing_issue_bits: list[str] = []
    if not has_timing_issue:
        missing_issue_bits.append("timing issue")
    if not has_order_issue:
        missing_issue_bits.append("reading-order issue")
    if not has_figure_issue:
        missing_issue_bits.append("figure/caption issue")
    if missing_issue_bits:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            confidence=confidence,
            violations_count=violations_count,
            passed=False,
            reason="did not surface: " + ", ".join(missing_issue_bits),
        )

    return ProbeResult(
        model_id=model.model_id,
        size_hint_b=model.size_hint_b,
        latency_s=latency_s,
        tokens_used=tokens_used,
        confidence=confidence,
        violations_count=violations_count,
        passed=True,
        reason="ok",
    )

