"""
Tournament orchestrator — full pipeline for one source document.

Wires together:
    classify → run_tournament → select_candidate → post-selection LLM audit → promote_winner

The winner's staging dir is copied to ``staging_root/winner/`` so downstream
code always reads from a stable path regardless of which adapter won.

Usage:
    from anydoc2md.format_converters.tournament.orchestrator import (
        run_full_tournament,
        TournamentResult,
        WINNER_DIR_NAME,
    )

    result = run_full_tournament(source_path, staging_root)
    if result.winner:
        print(f"Winner: {result.winner} → {result.winner_staging_dir}")
    else:
        print("All adapters disqualified — manual review needed")
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import (
    DocumentTraits,
    classify,
)
from anydoc2md.format_converters.tournament.runner import (
    default_adapter_names,
    run_tournament,
)
from anydoc2md.format_converters.tournament.audit import (
    CandidateAudit,
    MAX_AUDIT_ATTEMPTS,
    run_post_selection_audit_loop,
)
from anydoc2md.format_converters.tournament.remediation import (
    RemediationPlan,
)
from anydoc2md.format_converters.tournament.selector import (
    NEAR_TIE_THRESHOLD,
    SelectionResult,
    select_candidate,
)
from anydoc2md.llm_judge import JudgeVerdict
from anydoc2md.settings import (
    AUDIT_MODE_AUTO,
    AUDIT_MODE_LIGHT,
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
    normalize_audit_mode,
)

WINNER_DIR_NAME = "winner"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TournamentResult:
    """Outcome of the full tournament pipeline for one source document."""

    source_path: Path
    traits: DocumentTraits
    adapter_results: list[AdapterResult]
    selection: SelectionResult
    judge_verdict: JudgeVerdict | None
    remediation_plan: RemediationPlan | None
    audit_history: list[CandidateAudit]
    audit_mode: str
    winner: str | None
    winner_staging_dir: Path | None
    promoted: bool
    escalated: bool = False

    def to_dict(self) -> dict:
        return {
            "source_path": str(self.source_path),
            "winner": self.winner,
            "winner_staging_dir": str(self.winner_staging_dir) if self.winner_staging_dir else None,
            "promoted": self.promoted,
            "traits": self.traits.to_dict(),
            "selection": self.selection.to_dict(),
            "judge_verdict": self.judge_verdict.to_dict() if self.judge_verdict else None,
            "remediation_plan": self.remediation_plan.to_dict() if self.remediation_plan else None,
            "audit_history": [audit.to_dict() for audit in self.audit_history],
            "audit_mode": self.audit_mode,
            "adapter_timing_ms": {
                r.method_name: r.timing_ms for r in self.adapter_results
            },
            "escalated": self.escalated,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_full_tournament(
    source_path: Path,
    staging_root: Path,
    adapters: list[str] | None = None,
    *,
    near_tie_threshold: float = NEAR_TIE_THRESHOLD,
    judge_settings: JudgeSettings | None = None,
    audit_mode: str = AUDIT_MODE_AUTO,
    promote: bool = True,
    timeout_s: int = 600,
    max_audit_attempts: int = MAX_AUDIT_ATTEMPTS,
) -> TournamentResult:
    """
    Run the complete converter tournament for one source document.

    Pipeline stages:
      1. classify(source_path)              → DocumentTraits
      2. run_tournament(...)                → list[AdapterResult]
      3. select_candidate(...)              → SelectionResult
      4. audit ranked candidates            → final audited winner or escalation
      5. promote_winner(...) if promote     → copy winner dir to staging_root/winner/

    Args:
        source_path:        Source document to convert.
        staging_root:       Root dir; each adapter writes to staging_root/{name}/;
                            winner is promoted to staging_root/winner/.
        adapters:           Adapter names to run (default: inhouse only).
        near_tie_threshold: Score delta retained for backward-compatible ranking metadata.
        judge_settings:     Optional explicit settings for the LLM audit.
        audit_mode:         "auto" uses the judge when configured, otherwise
                            falls back to score-only light mode. "light" skips
                            the LLM audit and accepts the selected candidate.
        promote:            Copy winner staging dir to staging_root/winner/.
        timeout_s:          Per-adapter conversion timeout (seconds).
        max_audit_attempts: Maximum number of ranked candidates to audit before escalation.

    Returns:
        TournamentResult.  Never raises — failures are captured in result fields.
    """
    adapter_names = default_adapter_names() if adapters is None else list(adapters)
    normalized_audit_mode = normalize_audit_mode(audit_mode)
    staging_root.mkdir(parents=True, exist_ok=True)

    # Stage 1: classify
    traits = classify(source_path)

    # Stage 2: run all adapters
    adapter_results = run_tournament(
        source_path, staging_root, adapter_names, timeout_s=timeout_s,
    )

    # Stage 3: gate + score → select winner
    selection = select_candidate(source_path, staging_root, adapter_names,
                                 near_tie_threshold=near_tie_threshold)

    # Stage 4: audit the selected candidate, then retry lower-ranked candidates if needed.
    resolved_judge_settings = _resolve_judge_settings(
        audit_mode=normalized_audit_mode,
        judge_settings=judge_settings,
    )
    if normalized_audit_mode == AUDIT_MODE_LIGHT or resolved_judge_settings is None:
        audit_result = None
        judge_verdict = None
        remediation_plan = None
        winner = selection.candidate
    else:
        audit_result = run_post_selection_audit_loop(
            selection=selection,
            adapter_results=adapter_results,
            source_path=source_path,
            traits=traits,
            settings=resolved_judge_settings,
            max_attempts=max_audit_attempts,
            remediation_target_adapter="inhouse",
        )
        judge_verdict = audit_result.final_verdict
        remediation_plan = audit_result.remediation_plan
        winner = audit_result.winner

    # Stage 5: promote winner
    winner_staging_dir: Path | None = None
    promoted = False

    if winner and promote:
        src_dir = staging_root / winner
        dst_dir = staging_root / WINNER_DIR_NAME
        if src_dir.is_dir():
            _promote(src_dir, dst_dir)
            winner_staging_dir = dst_dir
            promoted = True
    elif winner:
        # promote=False: point at the adapter's own dir
        winner_staging_dir = staging_root / winner

    return TournamentResult(
        source_path=source_path,
        traits=traits,
        adapter_results=adapter_results,
        selection=selection,
        judge_verdict=judge_verdict,
        remediation_plan=remediation_plan,
        audit_history=[] if audit_result is None else audit_result.audits,
        audit_mode=normalized_audit_mode if resolved_judge_settings is not None else AUDIT_MODE_LIGHT,
        winner=winner,
        winner_staging_dir=winner_staging_dir,
        promoted=promoted,
        escalated=False if audit_result is None else audit_result.escalated,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _promote(src: Path, dst: Path) -> None:
    """Copy src dir to dst, replacing any existing dst."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _resolve_judge_settings(
    *,
    audit_mode: str,
    judge_settings: JudgeSettings | None,
) -> JudgeSettings | None:
    if audit_mode == AUDIT_MODE_LIGHT:
        return None
    if judge_settings is not None:
        return judge_settings
    try:
        return load_judge_settings_from_env()
    except AnyDocToMdConfigError:
        return None
