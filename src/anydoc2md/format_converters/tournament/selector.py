"""
Tournament selector — pick the best converter output from a completed tournament.

Flow:
    1. Run hard gates on every adapter's staging dir → disqualify failures.
    2. Score the surviving outputs with build_scorecard (lower = better).
    3. Rank by score; detect near-ties between winner and runner-up.
    4. Return a SelectionResult describing the winner and full ranking.

This module contains pure selection logic (select_from_results) for easy testing,
plus an integration entry-point (select_winner) that wires the full pipeline.

Usage:
    from anydoc2md.format_converters.tournament.selector import select_winner

    result = select_winner(source_path, staging_root, adapter_names=["inhouse", "docling"])
    if result.winner:
        print(result.winner, result.winner_score)
    else:
        print("All adapters disqualified")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from anydoc2md.output_qa.hard_gates import (
    HardGateResult,
    disqualified as gates_disqualified,
    first_failure,
    run_hard_gates,
)
from anydoc2md.output_qa.runner import run_all
from anydoc2md.output_qa.scoring import (
    ScoreCard,
    build_scorecard,
    rank_adapters,
)

# Adapters whose runner-up score is within this many points of the winner
# are flagged as a near-tie for human review (or LLM judging).
NEAR_TIE_THRESHOLD: float = 10.0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectionResult:
    """Outcome of running the selector over a set of adapter results."""

    winner: str | None                          # adapter name, or None if all disqualified
    winner_score: float                         # 0.0 when winner is None
    ranked: list[ScoreCard]                     # eligible adapters, best-first
    disqualified: dict[str, str]                # adapter → first gate failure reason
    near_tie: bool                              # runner-up within NEAR_TIE_THRESHOLD
    near_tie_adapters: list[str] = field(default_factory=list)  # names within threshold

    @property
    def all_disqualified(self) -> bool:
        return self.winner is None

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "winner_score": self.winner_score,
            "near_tie": self.near_tie,
            "near_tie_adapters": self.near_tie_adapters,
            "ranked": [c.to_dict() for c in self.ranked],
            "disqualified": self.disqualified,
        }


# ---------------------------------------------------------------------------
# Pure selection logic
# ---------------------------------------------------------------------------

def select_from_results(
    scorecards: list[ScoreCard],
    gate_results: dict[str, list[HardGateResult]],
    *,
    near_tie_threshold: float = NEAR_TIE_THRESHOLD,
) -> SelectionResult:
    """
    Select the best adapter from pre-computed scorecards and gate results.

    Args:
        scorecards:         One ScoreCard per adapter (only for gate-passing ones).
        gate_results:       {adapter_name: [HardGateResult]} for ALL adapters,
                            including those that were disqualified.
        near_tie_threshold: Score delta within which runner-up is flagged as near-tie.

    Returns:
        SelectionResult with winner, ranking, and near-tie info.
    """
    disq: dict[str, str] = {}
    for name, gates in gate_results.items():
        if gates_disqualified(gates):
            failure = first_failure(gates)
            disq[name] = failure.reason if failure else "Unknown gate failure"

    ranked = rank_adapters(scorecards)

    if not ranked:
        return SelectionResult(
            winner=None,
            winner_score=0.0,
            ranked=[],
            disqualified=disq,
            near_tie=False,
            near_tie_adapters=[],
        )

    winner_card = ranked[0]
    near_tie_adapters: list[str] = []
    near_tie = False

    if len(ranked) >= 2:
        for runner_up in ranked[1:]:
            delta = runner_up.total_score - winner_card.total_score
            if delta <= near_tie_threshold:
                near_tie = True
                near_tie_adapters.append(runner_up.adapter_name)
            else:
                break  # ranked in order — no need to continue once delta exceeds threshold

    return SelectionResult(
        winner=winner_card.adapter_name,
        winner_score=winner_card.total_score,
        ranked=ranked,
        disqualified=disq,
        near_tie=near_tie,
        near_tie_adapters=near_tie_adapters,
    )


# ---------------------------------------------------------------------------
# Integration entry-point
# ---------------------------------------------------------------------------

def select_winner(
    source_path: Path,
    staging_root: Path,
    adapter_names: list[str],
    *,
    near_tie_threshold: float = NEAR_TIE_THRESHOLD,
) -> SelectionResult:
    """
    Run gates + scoring against all adapter staging dirs and select a winner.

    Each adapter's staging dir is expected at staging_root/{adapter_name}/.
    Adapters whose staging dir has no index.md are automatically disqualified
    by the index_md_exists gate.

    Args:
        source_path:        Original source document (for Layer 2 checks).
        staging_root:       Parent dir containing per-adapter staging dirs.
        adapter_names:      Names of adapters to evaluate.
        near_tie_threshold: Score delta for near-tie detection.

    Returns:
        SelectionResult.  Never raises — errors in individual adapters produce
        disqualified entries.
    """
    gate_results: dict[str, list[HardGateResult]] = {}
    scorecards: list[ScoreCard] = []

    for name in adapter_names:
        staging_dir = staging_root / name
        gates = run_hard_gates(staging_dir, source_path)
        gate_results[name] = gates

        if gates_disqualified(gates):
            continue

        try:
            report = run_all(staging_dir, source_path)
            card = build_scorecard(report, name)
            scorecards.append(card)
        except Exception as exc:
            # Treat QA runner exceptions as a disqualifying error
            gate_results[name] = gates + [
                HardGateResult(
                    gate_name="qa_runner",
                    passed=False,
                    reason=f"QA runner failed: {exc}",
                )
            ]

    return select_from_results(
        scorecards, gate_results, near_tie_threshold=near_tie_threshold,
    )
