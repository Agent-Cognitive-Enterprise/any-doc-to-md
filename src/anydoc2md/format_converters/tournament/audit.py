"""
Post-selection LLM audit loop for tournament candidates.

This module separates score-based candidate selection from the later LLM audit
step. The selector chooses a ranked list of candidates; the audit loop then
walks that ranking, asking the LLM to accept or reject each candidate in turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.format_converters.tournament.remediation import (
    RemediationPlan,
    build_remediation_plan,
)
from anydoc2md.format_converters.tournament.render import render_markdown_to_audit_pdf
from anydoc2md.format_converters.tournament.selector import SelectionResult
from anydoc2md.llm_judge import JudgeVerdict, judge_candidate_against_source
from anydoc2md.settings import JudgeSettings

MAX_AUDIT_ATTEMPTS: int = 3
_MAJOR_SEVERITIES = {"critical", "major"}
_SEVERITY_WEIGHTS = {
    "critical": 25.0,
    "major": 12.0,
    "minor": 3.0,
}


@dataclass(frozen=True)
class CandidateAudit:
    adapter_name: str
    verdict: JudgeVerdict
    status: str  # accepted | rejected_major | audit_error_fallback
    penalty_points: float = 0.0
    rescored_total: float | None = None

    def to_dict(self) -> dict:
        return {
            "adapter_name": self.adapter_name,
            "status": self.status,
            "penalty_points": self.penalty_points,
            "rescored_total": self.rescored_total,
            "verdict": self.verdict.to_dict(),
        }


@dataclass(frozen=True)
class AuditLoopResult:
    winner: str | None
    final_verdict: JudgeVerdict | None
    remediation_plan: RemediationPlan | None
    audits: list[CandidateAudit] = field(default_factory=list)
    escalated: bool = False


def run_post_selection_audit_loop(
    *,
    selection: SelectionResult,
    adapter_results: list[AdapterResult],
    source_path: Path,
    traits: DocumentTraits,
    settings: JudgeSettings | None = None,
    max_attempts: int = MAX_AUDIT_ATTEMPTS,
    remediation_target_adapter: str = "inhouse",
) -> AuditLoopResult:
    """Audit ranked candidates until one is accepted or attempts are exhausted."""
    if selection.winner is None:
        return AuditLoopResult(
            winner=None,
            final_verdict=None,
            remediation_plan=None,
            audits=[],
            escalated=False,
        )

    by_name = {result.method_name: result for result in adapter_results}
    audits: list[CandidateAudit] = []
    plans: list[RemediationPlan] = []
    final_verdict: JudgeVerdict | None = None

    attempts = 0
    for scorecard in selection.ranked:
        if attempts >= max_attempts:
            break

        candidate = by_name.get(scorecard.adapter_name)
        if candidate is None:
            continue

        attempts += 1
        # Audit the same effective candidate Markdown that selection scored and
        # the CLI publishes: index_fixed.md when present, else raw index.md.
        # Otherwise the judge could penalize raw output that was never selected.
        fixed_md = candidate.staging_dir / "index_fixed.md"
        candidate_md = fixed_md if fixed_md.exists() else candidate.staging_dir / "index.md"
        audit_pdf_path = render_markdown_to_audit_pdf(
            candidate_md,
            candidate.staging_dir / "audit_candidate.pdf",
        )
        verdict = judge_candidate_against_source(
            candidate,
            source_path,
            traits,
            audit_pdf_path=audit_pdf_path,
            settings=settings,
        )
        final_verdict = verdict

        if not verdict.succeeded:
            audits.append(
                CandidateAudit(
                    adapter_name=candidate.method_name,
                    verdict=verdict,
                    status="audit_error_fallback",
                )
            )
            return AuditLoopResult(
                winner=candidate.method_name,
                final_verdict=verdict,
                remediation_plan=_merge_remediation_plans(
                    source_path=source_path,
                    target_adapter=remediation_target_adapter,
                    plans=plans,
                ),
                audits=audits,
                escalated=False,
            )

        if _has_major_findings(verdict):
            penalty_points = _penalty_points(verdict)
            rescored_total = scorecard.total_score + penalty_points
            next_score = _next_ranked_score(selection, scorecard.adapter_name)
            audits.append(
                CandidateAudit(
                    adapter_name=candidate.method_name,
                    verdict=verdict,
                    status=(
                        "accepted_penalized_major"
                        if next_score is None or rescored_total <= next_score
                        else "rejected_major"
                    ),
                    penalty_points=penalty_points,
                    rescored_total=rescored_total,
                )
            )
            plan = build_remediation_plan(
                source_path=source_path,
                candidates=[candidate],
                verdict=verdict,
                target_adapter=remediation_target_adapter,
            )
            if plan is not None:
                plans.append(plan)
            if next_score is None or rescored_total <= next_score:
                return AuditLoopResult(
                    winner=candidate.method_name,
                    final_verdict=verdict,
                    remediation_plan=_merge_remediation_plans(
                        source_path=source_path,
                        target_adapter=remediation_target_adapter,
                        plans=plans,
                    ),
                    audits=audits,
                    escalated=False,
                )
            continue

        audits.append(
            CandidateAudit(
                adapter_name=candidate.method_name,
                verdict=verdict,
                status="accepted",
            )
        )
        return AuditLoopResult(
            winner=candidate.method_name,
            final_verdict=verdict,
            remediation_plan=_merge_remediation_plans(
                source_path=source_path,
                target_adapter=remediation_target_adapter,
                plans=plans,
            ),
            audits=audits,
            escalated=False,
        )

    return AuditLoopResult(
        winner=None,
        final_verdict=final_verdict,
        remediation_plan=_merge_remediation_plans(
            source_path=source_path,
            target_adapter=remediation_target_adapter,
            plans=plans,
        ),
        audits=audits,
        escalated=bool(audits),
    )


def _has_major_findings(verdict: JudgeVerdict) -> bool:
    return any(violation.severity in _MAJOR_SEVERITIES for violation in verdict.violations)


def _penalty_points(verdict: JudgeVerdict) -> float:
    total = 0.0
    for violation in verdict.violations:
        total += _SEVERITY_WEIGHTS.get(violation.severity, 0.0) * max(1, violation.count)
    return total


def _next_ranked_score(selection: SelectionResult, adapter_name: str) -> float | None:
    for index, scorecard in enumerate(selection.ranked):
        if scorecard.adapter_name != adapter_name:
            continue
        if index + 1 >= len(selection.ranked):
            return None
        return selection.ranked[index + 1].total_score
    return None


def _merge_remediation_plans(
    *,
    source_path: Path,
    target_adapter: str,
    plans: list[RemediationPlan],
) -> RemediationPlan | None:
    if not plans:
        return None
    if len(plans) == 1:
        return plans[0]

    compare_against_values = sorted({plan.compare_against for plan in plans})
    preferred_values = sorted({plan.preferred_adapter for plan in plans if plan.preferred_adapter})
    merged_tasks = [task for plan in plans for task in plan.tasks]
    return RemediationPlan(
        source_path=str(source_path),
        target_adapter=target_adapter,
        preferred_adapter="multiple_candidates" if len(preferred_values) > 1 else (preferred_values[0] if preferred_values else ""),
        compare_against="multiple_candidates" if len(compare_against_values) > 1 else compare_against_values[0],
        summary=(
            f"{len(merged_tasks)} remediation task(s) collected from "
            f"{len(plans)} audited candidate(s)."
        ),
        tasks=merged_tasks,
    )
