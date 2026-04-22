"""Aggregation helpers for issue-focused PDF judge results."""

from __future__ import annotations

import re

from anydoc2md._llm_judge_types import JudgeVerdict, JudgeViolation, JudgeWindowVerdict


def aggregate_windowed_verdict(
    *,
    candidate_name: str,
    model_used: str,
    tokens_used: int,
    input_tokens: int,
    output_tokens: int,
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
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        violations=merged_violations,
        window_verdicts=window_verdicts,
        overall_confidence=_confidence_score(confidence),
        uncertainty_note=(
            "Violations aggregated from deterministic suspect windows and narrow issue review."
        ),
        error="",
    )


def normalize_window_pages(
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
