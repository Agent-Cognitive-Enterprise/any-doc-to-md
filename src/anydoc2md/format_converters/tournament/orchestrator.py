"""
Tournament orchestrator — full pipeline for one source document.

Wires together:
    classify → run_tournament → select_winner → [judge_near_tie] → promote_winner

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
    DEFAULT_ADAPTERS,
    run_tournament,
)
from anydoc2md.format_converters.tournament.selector import (
    NEAR_TIE_THRESHOLD,
    SelectionResult,
    select_winner,
)
from anydoc2md.llm_judge import (
    JudgeVerdict,
    judge_near_tie,
)
from anydoc2md.settings import JudgeSettings

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
    judge_verdict: JudgeVerdict | None     # None when no near-tie or judging skipped
    winner: str | None                     # final adapter name (may differ from selection.winner
                                           # when the judge overrides the score-based winner)
    winner_staging_dir: Path | None        # staging_root/winner/ after promotion; None if no winner
    promoted: bool                         # True when winner dir was copied to winner/

    def to_dict(self) -> dict:
        return {
            "source_path": str(self.source_path),
            "winner": self.winner,
            "winner_staging_dir": str(self.winner_staging_dir) if self.winner_staging_dir else None,
            "promoted": self.promoted,
            "traits": self.traits.to_dict(),
            "selection": self.selection.to_dict(),
            "judge_verdict": self.judge_verdict.to_dict() if self.judge_verdict else None,
            "adapter_timing_ms": {
                r.method_name: r.timing_ms for r in self.adapter_results
            },
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
    promote: bool = True,
    timeout_s: int = 600,
) -> TournamentResult:
    """
    Run the complete converter tournament for one source document.

    Pipeline stages:
      1. classify(source_path)              → DocumentTraits
      2. run_tournament(...)                → list[AdapterResult]
      3. select_winner(...)                 → SelectionResult
      4. judge_near_tie(...) if near_tie    → JudgeVerdict (winner override)
      5. promote_winner(...)  if promote    → copy winner dir to staging_root/winner/

    Args:
        source_path:        Source document to convert.
        staging_root:       Root dir; each adapter writes to staging_root/{name}/;
                            winner is promoted to staging_root/winner/.
        adapters:           Adapter names to run (default: inhouse, markitdown, docling).
        near_tie_threshold: Score delta below which the LLM judge is invoked.
        judge_settings:     Optional explicit settings for the near-tie judge.
        promote:            Copy winner staging dir to staging_root/winner/.
        timeout_s:          Per-adapter conversion timeout (seconds).

    Returns:
        TournamentResult.  Never raises — failures are captured in result fields.
    """
    adapter_names = adapters or DEFAULT_ADAPTERS
    staging_root.mkdir(parents=True, exist_ok=True)

    # Stage 1: classify
    traits = classify(source_path)

    # Stage 2: run all adapters
    adapter_results = run_tournament(
        source_path, staging_root, adapter_names, timeout_s=timeout_s,
    )

    # Stage 3: gate + score → select winner
    selection = select_winner(source_path, staging_root, adapter_names,
                              near_tie_threshold=near_tie_threshold)

    # Stage 4: LLM judge for near-ties
    judge_verdict: JudgeVerdict | None = None
    winner = selection.winner

    if selection.near_tie and winner is not None:
        tie_names = {winner} | set(selection.near_tie_adapters)
        candidates = [r for r in adapter_results if r.method_name in tie_names]
        judge_verdict = judge_near_tie(
            candidates, source_path, traits,
            settings=judge_settings,
        )
        if judge_verdict.succeeded:
            winner = judge_verdict.preferred_adapter

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
        winner=winner,
        winner_staging_dir=winner_staging_dir,
        promoted=promoted,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _promote(src: Path, dst: Path) -> None:
    """Copy src dir to dst, replacing any existing dst."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
