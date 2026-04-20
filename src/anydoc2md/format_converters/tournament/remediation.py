"""
Structured remediation plans derived from judge violations.

These plans are intended for an external coding-agent loop, not for the
runtime to modify code by itself. The pipeline persists them next to the
tournament report so a coding agent can inspect the source document, compare
candidate outputs, and turn the findings into tests and in-house fixes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.llm_judge import JudgeVerdict, JudgeViolation


@dataclass(frozen=True)
class RemediationTask:
    violation_type: str
    severity: str
    evidence: str
    pages: list[int]
    target_adapter: str
    compare_against: str
    suggested_test: str
    suggested_fix_area: str
    suggested_fix: str

    def to_dict(self) -> dict:
        return {
            "violation_type": self.violation_type,
            "severity": self.severity,
            "evidence": self.evidence,
            "pages": list(self.pages),
            "target_adapter": self.target_adapter,
            "compare_against": self.compare_against,
            "suggested_test": self.suggested_test,
            "suggested_fix_area": self.suggested_fix_area,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True)
class RemediationPlan:
    source_path: str
    target_adapter: str
    preferred_adapter: str
    compare_against: str
    summary: str
    tasks: list[RemediationTask] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "target_adapter": self.target_adapter,
            "preferred_adapter": self.preferred_adapter,
            "compare_against": self.compare_against,
            "summary": self.summary,
            "tasks": [task.to_dict() for task in self.tasks],
        }


_FIX_HINTS: dict[str, tuple[str, str, str]] = {
    "reading_order": (
        "Add a regression fixture that asserts paragraph and heading sequence for the affected pages.",
        "pdf_converter block ordering and multicolumn merge heuristics",
        "Adjust block sorting or column-merge logic so section flow matches the stronger candidate.",
    ),
    "missing_content": (
        "Add a fixture that checks key phrases from the affected pages survive conversion.",
        "pdf_converter text extraction / dropped-block filtering",
        "Relax over-aggressive block filtering or fallback extraction when content disappears.",
    ),
    "caption_detachment": (
        "Add a regression fixture that keeps figure captions adjacent to their images.",
        "pdf_converter image-caption association",
        "Preserve or reconstruct caption proximity during PDF block assembly.",
    ),
    "image_text_association": (
        "Add a regression fixture that keeps images near the surrounding explanatory text.",
        "pdf_converter image placement and surrounding block grouping",
        "Bind extracted image references to the nearest relevant text blocks instead of appending them late.",
    ),
    "table_fragmentation": (
        "Add a fixture that asserts table rows remain contiguous and ordered.",
        "pdf_converter table extraction and markdown rendering",
        "Improve table boundary detection or fallback rendering to avoid split rows and reordered cells.",
    ),
    "heading_hierarchy": (
        "Add a regression fixture that asserts heading levels and heading/body grouping.",
        "pdf_converter heading detection",
        "Tighten heading classification so visual heading cues do not fragment or flatten structure.",
    ),
    "duplicated_content": (
        "Add a fixture that fails on repeated long blocks or repeated running headers.",
        "pdf_converter de-duplication / repeated header stripping",
        "Strip repeated headers/footers and suppress duplicate block emission.",
    ),
}


def build_remediation_plan(
    *,
    source_path: Path,
    candidates: list[AdapterResult],
    verdict: JudgeVerdict,
    target_adapter: str = "inhouse",
) -> RemediationPlan | None:
    """Build a coding-agent remediation plan from judge violations."""
    if not verdict.violations:
        return None

    candidate_names = [candidate.method_name for candidate in candidates]
    effective_target = target_adapter if target_adapter in candidate_names else (
        verdict.preferred_adapter or candidate_names[0]
    )
    compare_against = verdict.preferred_adapter or next(
        (name for name in candidate_names if name != effective_target),
        effective_target,
    )

    tasks = [
        _build_task(
            violation=violation,
            target_adapter=effective_target,
            compare_against=compare_against,
        )
        for violation in verdict.violations
    ]
    summary = (
        f"{len(tasks)} remediation task(s) for {effective_target} derived from "
        f"judge findings against {compare_against}."
    )
    return RemediationPlan(
        source_path=str(source_path),
        target_adapter=effective_target,
        preferred_adapter=verdict.preferred_adapter,
        compare_against=compare_against,
        summary=summary,
        tasks=tasks,
    )


def _build_task(
    *,
    violation: JudgeViolation,
    target_adapter: str,
    compare_against: str,
) -> RemediationTask:
    suggested_test, suggested_fix_area, suggested_fix = _FIX_HINTS.get(
        violation.type,
        (
            "Add a focused regression fixture that reproduces the cited failure pattern.",
            "inhouse conversion post-processing",
            "Inspect the cited evidence and align in-house conversion output with the stronger candidate.",
        ),
    )
    return RemediationTask(
        violation_type=violation.type,
        severity=violation.severity,
        evidence=violation.evidence,
        pages=list(violation.pages),
        target_adapter=target_adapter,
        compare_against=compare_against,
        suggested_test=suggested_test,
        suggested_fix_area=suggested_fix_area,
        suggested_fix=suggested_fix,
    )
