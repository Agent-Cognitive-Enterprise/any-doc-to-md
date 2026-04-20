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


@dataclass(frozen=True)
class CandidateAudit:
    adapter_name: str
    verdict: JudgeVerdict
    status: str  # accepted | rejected_major | audit_error_fallback

    def to_dict(self) -> dict:
        return {
            "adapter_name": self.adapter_name,
            "status": self.status,
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
        audit_pdf_path = render_markdown_to_audit_pdf(
            candidate.staging_dir / "index.md",
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
            audits.append(
                CandidateAudit(
                    adapter_name=candidate.method_name,
                    verdict=verdict,
                    status="rejected_major",
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
