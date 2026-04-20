"""
Tests for format_converters/tournament/orchestrator.py.

All heavy I/O (classify, run_tournament, select_winner, judge_near_tie) is
mocked so tests run without live adapters or LM Studio.

Covers:
  - TournamentResult contract (to_dict keys)
  - Single clear winner — judge not called, winner promoted
  - Near-tie — judge called, judge winner adopted
  - Near-tie — judge fails — score winner kept as fallback
  - All adapters disqualified — no winner, no promotion
  - promote=False — winner_staging_dir points to adapter dir, no copy
  - promote=True  — winner dir is actually copied on disk
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import (
    DocumentTraits,
    _unknown_traits,
)
from anydoc2md.format_converters.tournament.orchestrator import (
    WINNER_DIR_NAME,
    TournamentResult,
    run_full_tournament,
)
from anydoc2md.format_converters.tournament.selector import SelectionResult
from anydoc2md.llm_judge import JudgeVerdict
from anydoc2md.output_qa.scoring import ScoreCard
from anydoc2md.settings import JudgeSettings


# =========================================================================== #
# Helpers
# =========================================================================== #

def _traits(**kw) -> DocumentTraits:
    defaults = dict(
        file_type="pdf", page_count=5, image_count=2, table_count=1,
        word_count=500, is_scanned=False, is_image_heavy=False,
        is_table_heavy=False, is_multi_column=False,
        is_text_only=False, has_math=False,
    )
    defaults.update(kw)
    return DocumentTraits(**defaults)


def _scorecard(name: str, score: float = 0.0) -> ScoreCard:
    return ScoreCard(
        adapter_name=name,
        total_score=score,
        check_scores={},
        fail_count=0,
        warn_count=0,
        pass_count=1,
    )


def _adapter_result(name: str, staging_root: Path, md: str = "# Doc") -> AdapterResult:
    staging = staging_root / name
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "index.md").write_text(md, encoding="utf-8")
    return AdapterResult(
        method_name=name, method_version="1",
        command_invoked="", exit_code=0,
        staging_dir=staging, timing_ms=10, status="ok",
    )


def _selection(winner: str, ranked_names: list[str],
               near_tie: bool = False,
               near_tie_adapters: list[str] | None = None) -> SelectionResult:
    ranked = [_scorecard(n, float(i)) for i, n in enumerate(ranked_names)]
    return SelectionResult(
        winner=winner,
        winner_score=0.0,
        ranked=ranked,
        disqualified={},
        near_tie=near_tie,
        near_tie_adapters=near_tie_adapters or [],
    )


def _verdict(preferred: str, confidence: str = "high") -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=preferred,
        confidence=confidence,
        reasoning="Good output.",
        notes={preferred: "Best."},
        model_used="test-model",
        tokens_used=100,
    )


def _judge_settings() -> JudgeSettings:
    return JudgeSettings(
        url="http://localhost:1234/v1",
        model="qwen/qwen3.6-35b-a3b",
    )


def _error_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter="", confidence="error",
        reasoning="", notes={},
        model_used="test-model", tokens_used=0,
        error="Network failure",
    )


MOCK_BASE = "anydoc2md.format_converters.tournament.orchestrator"


def _patch_all(
    tmp_path: Path,
    *,
    adapter_names: list[str],
    selection: SelectionResult,
    verdict: JudgeVerdict | None = None,
    traits: DocumentTraits | None = None,
):
    """
    Context manager that patches classify, run_tournament, select_winner,
    and judge_near_tie for the orchestrator module.

    Returns (patches_context, adapter_results_list).
    """
    t = traits or _traits()
    adapters = [_adapter_result(n, tmp_path) for n in adapter_names]

    classify_mock = patch(f"{MOCK_BASE}.classify", return_value=t)
    tournament_mock = patch(f"{MOCK_BASE}.run_tournament", return_value=adapters)
    selector_mock = patch(f"{MOCK_BASE}.select_winner", return_value=selection)
    judge_mock = patch(f"{MOCK_BASE}.judge_near_tie",
                       return_value=(verdict or _error_verdict()))

    return classify_mock, tournament_mock, selector_mock, judge_mock, adapters, t


# =========================================================================== #
# TournamentResult contract
# =========================================================================== #

class TestTournamentResultContract:
    def test_to_dict_has_required_keys(self, tmp_path: Path) -> None:
        r = TournamentResult(
            source_path=tmp_path / "doc.pdf",
            traits=_traits(),
            adapter_results=[],
            selection=_selection("a", ["a"]),
            judge_verdict=None,
            winner="a",
            winner_staging_dir=tmp_path / WINNER_DIR_NAME,
            promoted=True,
        )
        d = r.to_dict()
        for k in ("source_path", "winner", "winner_staging_dir", "promoted",
                  "traits", "selection", "judge_verdict", "adapter_timing_ms"):
            assert k in d, f"Missing key: {k}"

    def test_to_dict_judge_verdict_none_when_no_tie(self, tmp_path: Path) -> None:
        r = TournamentResult(
            source_path=tmp_path / "doc.pdf",
            traits=_traits(),
            adapter_results=[],
            selection=_selection("a", ["a"]),
            judge_verdict=None,
            winner="a",
            winner_staging_dir=None,
            promoted=False,
        )
        assert r.to_dict()["judge_verdict"] is None

    def test_to_dict_winner_staging_dir_none_when_no_winner(self, tmp_path: Path) -> None:
        sel = SelectionResult(
            winner=None, winner_score=0.0, ranked=[], disqualified={"a": "empty"},
            near_tie=False, near_tie_adapters=[],
        )
        r = TournamentResult(
            source_path=tmp_path / "doc.pdf",
            traits=_traits(),
            adapter_results=[],
            selection=sel,
            judge_verdict=None,
            winner=None,
            winner_staging_dir=None,
            promoted=False,
        )
        assert r.to_dict()["winner_staging_dir"] is None


# =========================================================================== #
# Single clear winner (no near-tie)
# =========================================================================== #

class TestSingleWinner:
    def test_winner_set_correctly(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse", "markitdown"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, adapters, t = _patch_all(
            tmp_path, adapter_names=["inhouse", "markitdown"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p as judge_mock:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner == "inhouse"
        judge_mock.assert_not_called()

    def test_judge_not_called_when_no_near_tie(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p as judge_mock:
            run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        judge_mock.assert_not_called()

    def test_judge_verdict_is_none_when_no_near_tie(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.judge_verdict is None

    def test_winner_dir_promoted(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, adapters, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        # Make sure the adapter staging dir exists (our _adapter_result creates it under tmp_path)
        # We need the staging dir to match what orchestrator will use (staging/inhouse/index.md)
        (staging / "inhouse").mkdir(parents=True, exist_ok=True)
        (staging / "inhouse" / "index.md").write_text("# Inhouse", encoding="utf-8")

        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", staging)

        assert result.promoted is True
        assert result.winner_staging_dir == staging / WINNER_DIR_NAME
        assert (staging / WINNER_DIR_NAME / "index.md").exists()


# =========================================================================== #
# Near-tie — judge called
# =========================================================================== #

class TestNearTieWithJudge:
    def test_judge_called_on_near_tie(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        v = _verdict("docling")
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"], selection=sel, verdict=v,
        )
        with classify_p, tour_p, sel_p, judge_p as judge_mock:
            run_full_tournament(
                tmp_path / "doc.pdf",
                tmp_path / "staging",
                judge_settings=_judge_settings(),
            )
        judge_mock.assert_called_once()

    def test_judge_winner_overrides_score_winner(self, tmp_path: Path) -> None:
        # Score winner = inhouse; judge picks docling
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        v = _verdict("docling")
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"], selection=sel, verdict=v,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner == "docling"

    def test_judge_verdict_stored_on_result(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        v = _verdict("docling", confidence="medium")
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"], selection=sel, verdict=v,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.judge_verdict is not None
        assert result.judge_verdict.confidence == "medium"

    def test_near_tie_candidates_include_score_winner(self, tmp_path: Path) -> None:
        """The judge must receive the score winner + near-tie adapters as candidates."""
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"],
            selection=sel, verdict=_verdict("inhouse"),
        )
        with classify_p, tour_p, sel_p, judge_p as judge_mock:
            run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        call_args = judge_mock.call_args
        candidates = call_args[0][0]
        names = {c.method_name for c in candidates}
        assert "inhouse" in names
        assert "docling" in names


# =========================================================================== #
# Near-tie — judge fails → score winner kept
# =========================================================================== #

class TestNearTieJudgeFails:
    def test_score_winner_kept_on_judge_error(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"],
            selection=sel, verdict=_error_verdict(),
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        # Judge failed → fall back to score winner
        assert result.winner == "inhouse"

    def test_error_verdict_stored(self, tmp_path: Path) -> None:
        sel = _selection("inhouse", ["inhouse", "docling"],
                         near_tie=True, near_tie_adapters=["docling"])
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"],
            selection=sel, verdict=_error_verdict(),
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.judge_verdict is not None
        assert not result.judge_verdict.succeeded


# =========================================================================== #
# All adapters disqualified
# =========================================================================== #

class TestAllDisqualified:
    def test_winner_is_none(self, tmp_path: Path) -> None:
        sel = SelectionResult(
            winner=None, winner_score=0.0, ranked=[],
            disqualified={"inhouse": "empty", "docling": "empty"},
            near_tie=False, near_tie_adapters=[],
        )
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse", "docling"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner is None
        assert result.winner_staging_dir is None
        assert result.promoted is False

    def test_judge_not_called_when_all_disqualified(self, tmp_path: Path) -> None:
        sel = SelectionResult(
            winner=None, winner_score=0.0, ranked=[],
            disqualified={"inhouse": "empty"},
            near_tie=False, near_tie_adapters=[],
        )
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p as judge_mock:
            run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        judge_mock.assert_not_called()


# =========================================================================== #
# promote=False
# =========================================================================== #

class TestPromoteFalse:
    def test_no_winner_dir_created(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", staging,
                                         promote=False)
        assert result.promoted is False
        assert not (staging / WINNER_DIR_NAME).exists()

    def test_winner_staging_dir_points_to_adapter_dir(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", staging,
                                         promote=False)
        assert result.winner_staging_dir == staging / "inhouse"


# =========================================================================== #
# Promote=True — filesystem behaviour
# =========================================================================== #

class TestPromoteFilesystem:
    def test_winner_dir_contains_index_md(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        # Create real adapter dir with content
        (staging / "docling").mkdir(parents=True)
        (staging / "docling" / "index.md").write_text("# Docling", encoding="utf-8")

        sel = _selection("docling", ["docling"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["docling"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            result = run_full_tournament(tmp_path / "doc.pdf", staging)

        assert result.promoted is True
        winner_md = staging / WINNER_DIR_NAME / "index.md"
        assert winner_md.exists()
        assert winner_md.read_text() == "# Docling"

    def test_previous_winner_dir_replaced(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        (staging / "inhouse").mkdir(parents=True)
        (staging / "inhouse" / "index.md").write_text("# Inhouse v2", encoding="utf-8")
        # Pre-existing winner dir from an old run
        (staging / WINNER_DIR_NAME).mkdir(parents=True)
        (staging / WINNER_DIR_NAME / "index.md").write_text("# Old winner", encoding="utf-8")

        sel = _selection("inhouse", ["inhouse"], near_tie=False)
        classify_p, tour_p, sel_p, judge_p, _, _ = _patch_all(
            tmp_path, adapter_names=["inhouse"], selection=sel,
        )
        with classify_p, tour_p, sel_p, judge_p:
            run_full_tournament(tmp_path / "doc.pdf", staging)

        assert (staging / WINNER_DIR_NAME / "index.md").read_text() == "# Inhouse v2"

