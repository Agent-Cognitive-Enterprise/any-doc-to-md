"""
Tests for format_converters/tournament/selector.py.

Pure logic (select_from_results) is tested exhaustively with constructed
ScoreCard/HardGateResult objects — no real PDF/staging dirs required.

Integration (select_winner) is tested with actual tmp_path staging dirs
containing a valid index.md, exercising the full gate → score → select chain.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from anydoc2md.output_qa.hard_gates import HardGateResult
from anydoc2md.output_qa.scoring import ScoreCard
from anydoc2md.format_converters.tournament.selector import (
    NEAR_TIE_THRESHOLD,
    SelectionResult,
    select_from_results,
    select_winner,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _card(name: str, score: float) -> ScoreCard:
    return ScoreCard(
        adapter_name=name,
        total_score=score,
        check_scores={},
        fail_count=0,
        warn_count=0,
        pass_count=1,
    )


def _pass_gates(name: str) -> list[HardGateResult]:
    return [HardGateResult(gate_name="index_md_exists", passed=True)]


def _fail_gates(name: str, reason: str = "No index.md") -> list[HardGateResult]:
    return [HardGateResult(gate_name="index_md_exists", passed=False, reason=reason)]


def _staging(tmp_path: Path, name: str, md: str | None = None) -> Path:
    """Create a minimal valid staging dir for one adapter."""
    d = tmp_path / name
    d.mkdir()
    (d / "images").mkdir()
    content = md if md is not None else "# Title\n\n" + "word " * 40
    (d / "index.md").write_text(content, encoding="utf-8")
    return d


# =========================================================================== #
# SelectionResult contract
# =========================================================================== #

class TestSelectionResult:
    def test_to_dict_keys(self) -> None:
        r = SelectionResult(
            winner="inhouse", winner_score=0.0,
            ranked=[], disqualified={}, near_tie=False,
        )
        d = r.to_dict()
        for k in ("winner", "winner_score", "near_tie", "near_tie_adapters",
                  "ranked", "disqualified"):
            assert k in d

    def test_all_disqualified_property(self) -> None:
        r = SelectionResult(
            winner=None, winner_score=0.0,
            ranked=[], disqualified={"a": "reason"}, near_tie=False,
        )
        assert r.all_disqualified is True

    def test_all_disqualified_false_when_winner(self) -> None:
        r = SelectionResult(
            winner="inhouse", winner_score=0.0,
            ranked=[], disqualified={}, near_tie=False,
        )
        assert r.all_disqualified is False


# =========================================================================== #
# select_from_results — winner selection
# =========================================================================== #

class TestSelectFromResults:
    def test_clear_winner_selected(self) -> None:
        cards = [_card("a", 0.0), _card("b", 30.0)]
        gates = {"a": _pass_gates("a"), "b": _pass_gates("b")}
        result = select_from_results(cards, gates)
        assert result.winner == "a"
        assert result.winner_score == 0.0

    def test_all_disqualified_returns_none_winner(self) -> None:
        gates = {"a": _fail_gates("a"), "b": _fail_gates("b")}
        result = select_from_results([], gates)
        assert result.winner is None
        assert result.all_disqualified is True

    def test_disqualified_dict_populated(self) -> None:
        gates = {
            "a": _pass_gates("a"),
            "b": _fail_gates("b", "No index.md found."),
        }
        result = select_from_results([_card("a", 0.0)], gates)
        assert "b" in result.disqualified
        assert "index.md" in result.disqualified["b"].lower()

    def test_ranked_list_ordered_ascending(self) -> None:
        cards = [_card("b", 20.0), _card("a", 0.0), _card("c", 10.0)]
        gates = {n: _pass_gates(n) for n in ("a", "b", "c")}
        result = select_from_results(cards, gates)
        assert [c.adapter_name for c in result.ranked] == ["a", "c", "b"]

    def test_disqualified_not_in_ranked(self) -> None:
        cards = [_card("a", 0.0)]  # b was disqualified, not scored
        gates = {"a": _pass_gates("a"), "b": _fail_gates("b")}
        result = select_from_results(cards, gates)
        names_in_ranked = {c.adapter_name for c in result.ranked}
        assert "b" not in names_in_ranked

    def test_empty_scorecards_and_empty_gates(self) -> None:
        result = select_from_results([], {})
        assert result.winner is None
        assert result.ranked == []
        assert result.disqualified == {}


# =========================================================================== #
# select_from_results — near-tie detection
# =========================================================================== #

class TestNearTieDetection:
    def test_no_near_tie_when_gap_exceeds_threshold(self) -> None:
        cards = [_card("a", 0.0), _card("b", NEAR_TIE_THRESHOLD + 1)]
        gates = {n: _pass_gates(n) for n in ("a", "b")}
        result = select_from_results(cards, gates)
        assert result.near_tie is False
        assert result.near_tie_adapters == []

    def test_near_tie_at_threshold_boundary(self) -> None:
        cards = [_card("a", 0.0), _card("b", NEAR_TIE_THRESHOLD)]
        gates = {n: _pass_gates(n) for n in ("a", "b")}
        result = select_from_results(cards, gates)
        assert result.near_tie is True
        assert "b" in result.near_tie_adapters

    def test_near_tie_with_exact_tie(self) -> None:
        cards = [_card("a", 0.0), _card("b", 0.0)]
        gates = {n: _pass_gates(n) for n in ("a", "b")}
        result = select_from_results(cards, gates)
        assert result.near_tie is True
        assert "b" in result.near_tie_adapters

    def test_three_way_tie_all_flagged(self) -> None:
        cards = [_card("a", 0.0), _card("b", 0.0), _card("c", 0.0)]
        gates = {n: _pass_gates(n) for n in ("a", "b", "c")}
        result = select_from_results(cards, gates)
        assert result.near_tie is True
        assert set(result.near_tie_adapters) == {"b", "c"}

    def test_only_close_runners_up_flagged(self) -> None:
        # a=0, b=5 (close), c=50 (far) — only b should be flagged
        cards = [_card("a", 0.0), _card("b", 5.0), _card("c", 50.0)]
        gates = {n: _pass_gates(n) for n in ("a", "b", "c")}
        result = select_from_results(cards, gates, near_tie_threshold=10.0)
        assert "b" in result.near_tie_adapters
        assert "c" not in result.near_tie_adapters

    def test_no_near_tie_with_single_adapter(self) -> None:
        cards = [_card("a", 0.0)]
        gates = {"a": _pass_gates("a")}
        result = select_from_results(cards, gates)
        assert result.near_tie is False

    def test_custom_threshold_honoured(self) -> None:
        cards = [_card("a", 0.0), _card("b", 5.0)]
        gates = {n: _pass_gates(n) for n in ("a", "b")}
        # threshold=3 → 5 > 3 → no near-tie
        r1 = select_from_results(cards, gates, near_tie_threshold=3.0)
        assert r1.near_tie is False
        # threshold=6 → 5 ≤ 6 → near-tie
        r2 = select_from_results(cards, gates, near_tie_threshold=6.0)
        assert r2.near_tie is True


# =========================================================================== #
# select_winner — integration (real staging dirs, no source PDF)
# =========================================================================== #

class TestSelectWinner:
    def test_selects_only_eligible_adapter(self, tmp_path: Path) -> None:
        _staging(tmp_path, "good")
        # "bad" has no index.md → gate fail
        (tmp_path / "bad").mkdir()
        result = select_winner(None, tmp_path, ["good", "bad"])
        assert result.winner == "good"
        assert "bad" in result.disqualified

    def test_all_disqualified_when_no_index_md(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        result = select_winner(None, tmp_path, ["a", "b"])
        assert result.winner is None
        assert len(result.disqualified) == 2

    def test_single_eligible_adapter_wins(self, tmp_path: Path) -> None:
        _staging(tmp_path, "only")
        result = select_winner(None, tmp_path, ["only"])
        assert result.winner == "only"
        assert result.winner_score == 0.0

    def test_empty_adapter_list(self, tmp_path: Path) -> None:
        result = select_winner(None, tmp_path, [])
        assert result.winner is None
        assert result.ranked == []

    def test_two_equal_adapters_tie_detected(self, tmp_path: Path) -> None:
        _staging(tmp_path, "alpha")
        _staging(tmp_path, "beta")
        result = select_winner(None, tmp_path, ["alpha", "beta"])
        assert result.near_tie is True
        assert result.winner is not None  # one selected (alpha, alphabetically)

    def test_winner_is_in_ranked(self, tmp_path: Path) -> None:
        _staging(tmp_path, "a")
        _staging(tmp_path, "b")
        result = select_winner(None, tmp_path, ["a", "b"])
        names = [c.adapter_name for c in result.ranked]
        assert result.winner in names

    def test_missing_staging_dir_disqualified(self, tmp_path: Path) -> None:
        _staging(tmp_path, "present")
        # "absent" staging dir doesn't exist at all
        result = select_winner(None, tmp_path, ["present", "absent"])
        assert result.winner == "present"
        assert "absent" in result.disqualified

    def test_to_dict_is_json_serialisable(self, tmp_path: Path) -> None:
        import json
        _staging(tmp_path, "x")
        result = select_winner(None, tmp_path, ["x"])
        # Should not raise
        json.dumps(result.to_dict())

    def test_paragraph_fragmentation_score_prefers_clean_adapter(
        self,
        tmp_path: Path,
    ) -> None:
        _staging(tmp_path, "fragmented", _row_sliced_fixture())
        _staging(
            tmp_path,
            "clean",
            (
                "The inspection team arrived at the north intake after the first alarm "
                "and found stable readings.\n\n"
                "The operator reviewed the morning log and found no missing values.\n"
            ),
        )

        result = select_winner(None, tmp_path, ["fragmented", "clean"])

        assert result.winner == "clean"
        by_name = {card.adapter_name: card for card in result.ranked}
        assert by_name["clean"].check_scores["paragraph_not_row_sliced"] == 0.0
        assert by_name["fragmented"].check_scores["paragraph_not_row_sliced"] > 0.0

    def test_non_ok_adapter_result_sidecar_disqualifies_late_index_md(
        self,
        tmp_path: Path,
    ) -> None:
        _staging(tmp_path, "late_timeout")
        (tmp_path / "late_timeout" / "adapter_result.json").write_text(
            json.dumps({
                "method_name": "late_timeout",
                "status": "timeout",
                "error_message": "Adapter did not complete within wall-clock timeout",
            }),
            encoding="utf-8",
        )

        result = select_winner(None, tmp_path, ["late_timeout"])

        assert result.winner is None
        assert result.ranked == []
        assert "late_timeout" in result.disqualified
        assert "timeout" in result.disqualified["late_timeout"]

    def test_missing_adapter_result_sidecar_preserves_staging_only_selection(
        self,
        tmp_path: Path,
    ) -> None:
        _staging(tmp_path, "legacy")

        result = select_winner(None, tmp_path, ["legacy"])

        assert result.winner == "legacy"


def _row_sliced_fixture() -> str:
    return "\n\n".join(
        [
            "The inspection team arrived at the north intake",
            "after the first alarm and found that the overflow",
            "channel was carrying shallow water across the grated",
            "walkway while the upstream valve remained partially",
            "open and the temporary pump continued cycling",
            "every few minutes without recording a stable",
            "pressure reading.",
            "The operator reported that the same pattern",
            "had appeared during the previous storm and that",
            "the manual log showed brief pressure drops",
            "near the east manifold whenever the backup",
            "generator switched load while the",
            "backup pump continued running.",
        ]
    ) + "\n"
