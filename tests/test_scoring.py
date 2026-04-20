"""
Tests for output_qa/scoring.py.

Verifies:
  - score_check: pass=0, warn/fail with and without details
  - violation_multiplier capping at MAX_VIOLATION_MULTIPLIER
  - unknown check names fall back to DEFAULT_CHECK_WEIGHT
  - build_scorecard aggregates correctly from a QAReport
  - rank_adapters: ascending order, deterministic tie-break
  - ScoreCard properties (check_count, to_dict)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from anydoc2md.output_qa.checks import CheckResult
from anydoc2md.output_qa.runner import QAReport
from anydoc2md.output_qa.scoring import (
    CHECK_WEIGHTS,
    DEFAULT_CHECK_WEIGHT,
    MAX_VIOLATION_MULTIPLIER,
    SEVERITY_WEIGHTS,
    ScoreCard,
    build_scorecard,
    rank_adapters,
    score_check,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _check(name: str, status: str, details: list[str] | None = None) -> CheckResult:
    return CheckResult(name=name, layer=1, status=status,
                       message="", details=details or [])


def _report(*checks: CheckResult) -> QAReport:
    return QAReport(staging_dir="/tmp/s", source="", checks=list(checks))


def _card(score: float, name: str = "adapter") -> ScoreCard:
    return ScoreCard(
        adapter_name=name,
        total_score=score,
        check_scores={},
        fail_count=0,
        warn_count=0,
        pass_count=1,
    )


# =========================================================================== #
# score_check
# =========================================================================== #

class TestScoreCheck:
    def test_pass_always_zero(self) -> None:
        assert score_check(_check("text_coverage", "pass")) == 0.0

    def test_warn_no_details(self) -> None:
        # warn with no details → multiplier=1
        c = _check("no_repeated_headings", "warn")
        expected = CHECK_WEIGHTS["no_repeated_headings"] * SEVERITY_WEIGHTS["warn"] * 1
        assert score_check(c) == pytest.approx(expected)

    def test_fail_no_details(self) -> None:
        c = _check("images_locally_resolvable", "fail")
        expected = CHECK_WEIGHTS["images_locally_resolvable"] * SEVERITY_WEIGHTS["fail"] * 1
        assert score_check(c) == pytest.approx(expected)

    def test_multiplier_scales_with_detail_count(self) -> None:
        c3 = _check("no_double_bullets", "fail", ["a", "b", "c"])
        c1 = _check("no_double_bullets", "fail", ["a"])
        assert score_check(c3) == pytest.approx(score_check(c1) * 3)

    def test_multiplier_capped_at_max(self) -> None:
        many_details = [str(i) for i in range(MAX_VIOLATION_MULTIPLIER + 5)]
        capped = _check("no_double_bullets", "fail", many_details)
        at_cap = _check("no_double_bullets", "fail",
                        [str(i) for i in range(MAX_VIOLATION_MULTIPLIER)])
        assert score_check(capped) == pytest.approx(score_check(at_cap))

    def test_unknown_check_uses_default_weight(self) -> None:
        c = _check("brand_new_check", "fail")
        expected = DEFAULT_CHECK_WEIGHT * SEVERITY_WEIGHTS["fail"] * 1
        assert score_check(c) == pytest.approx(expected)

    def test_unknown_status_returns_zero(self) -> None:
        c = _check("text_coverage", "skip")
        assert score_check(c) == 0.0

    def test_text_coverage_fail_weighted_highly(self) -> None:
        # text_coverage weight=5, images_locally_resolvable weight=5
        # Both are high-weight; fail with 1 detail each should be equal
        tc = score_check(_check("text_coverage", "fail", ["word"]))
        ilr = score_check(_check("images_locally_resolvable", "fail", ["img.png"]))
        assert tc == pytest.approx(ilr)

    def test_caption_near_image_fail_outweighs_image_size_warn(self) -> None:
        caption = score_check(_check("caption_near_image", "fail"))
        size = score_check(_check("image_size_plausible", "warn"))
        assert caption > size


# =========================================================================== #
# build_scorecard
# =========================================================================== #

class TestBuildScorecard:
    def test_perfect_report_scores_zero(self) -> None:
        report = _report(
            _check("no_double_bullets", "pass"),
            _check("text_coverage", "pass"),
        )
        card = build_scorecard(report, "inhouse")
        assert card.total_score == 0.0

    def test_adapter_name_stored(self) -> None:
        card = build_scorecard(_report(_check("text_coverage", "pass")), "docling")
        assert card.adapter_name == "docling"

    def test_counts_by_status(self) -> None:
        report = _report(
            _check("no_double_bullets", "pass"),
            _check("no_repeated_headings", "warn"),
            _check("images_locally_resolvable", "fail"),
        )
        card = build_scorecard(report, "x")
        assert card.pass_count == 1
        assert card.warn_count == 1
        assert card.fail_count == 1

    def test_total_is_sum_of_per_check(self) -> None:
        report = _report(
            _check("no_double_bullets", "fail", ["a", "b"]),
            _check("text_coverage", "warn"),
        )
        card = build_scorecard(report, "x")
        expected = (
            score_check(_check("no_double_bullets", "fail", ["a", "b"]))
            + score_check(_check("text_coverage", "warn"))
        )
        assert card.total_score == pytest.approx(expected)

    def test_check_scores_keys_match_check_names(self) -> None:
        report = _report(
            _check("no_double_bullets", "pass"),
            _check("text_coverage", "fail"),
        )
        card = build_scorecard(report, "x")
        assert set(card.check_scores) == {"no_double_bullets", "text_coverage"}

    def test_check_count_property(self) -> None:
        report = _report(
            _check("a", "pass"),
            _check("b", "warn"),
            _check("c", "fail"),
        )
        card = build_scorecard(report, "x")
        assert card.check_count == 3

    def test_to_dict_keys(self) -> None:
        card = build_scorecard(_report(_check("text_coverage", "pass")), "x")
        d = card.to_dict()
        for k in ("adapter_name", "total_score", "check_scores",
                  "check_count", "fail_count", "warn_count", "pass_count"):
            assert k in d

    def test_duplicate_check_names_last_wins(self) -> None:
        # If two checks share a name (shouldn't happen in practice), last one wins
        report = _report(
            _check("no_double_bullets", "fail"),
            _check("no_double_bullets", "pass"),
        )
        card = build_scorecard(report, "x")
        # second entry (pass) overwrites first (fail) in check_scores dict
        assert card.check_scores["no_double_bullets"] == 0.0
        # but counts include both
        assert card.fail_count == 1
        assert card.pass_count == 1


# =========================================================================== #
# rank_adapters
# =========================================================================== #

class TestRankAdapters:
    def test_sorted_ascending_by_score(self) -> None:
        cards = [_card(30.0, "c"), _card(0.0, "a"), _card(10.0, "b")]
        ranked = rank_adapters(cards)
        assert [c.adapter_name for c in ranked] == ["a", "b", "c"]

    def test_tie_broken_alphabetically(self) -> None:
        cards = [_card(5.0, "zebra"), _card(5.0, "alpha"), _card(5.0, "mid")]
        ranked = rank_adapters(cards)
        assert ranked[0].adapter_name == "alpha"
        assert ranked[-1].adapter_name == "zebra"

    def test_single_card_returned(self) -> None:
        cards = [_card(42.0, "only")]
        assert rank_adapters(cards)[0].adapter_name == "only"

    def test_empty_list_returned(self) -> None:
        assert rank_adapters([]) == []

    def test_does_not_mutate_input(self) -> None:
        cards = [_card(10.0, "b"), _card(0.0, "a")]
        original_order = [c.adapter_name for c in cards]
        rank_adapters(cards)
        assert [c.adapter_name for c in cards] == original_order

    def test_all_zero_scores_preserves_all(self) -> None:
        cards = [_card(0.0, n) for n in ("c", "a", "b")]
        ranked = rank_adapters(cards)
        assert len(ranked) == 3
        assert ranked[0].adapter_name == "a"


# =========================================================================== #
# Weight table sanity checks
# =========================================================================== #

class TestWeightTables:
    def test_severity_weights_have_all_statuses(self) -> None:
        for s in ("pass", "warn", "fail"):
            assert s in SEVERITY_WEIGHTS

    def test_pass_severity_is_zero(self) -> None:
        assert SEVERITY_WEIGHTS["pass"] == 0.0

    def test_fail_outweighs_warn(self) -> None:
        assert SEVERITY_WEIGHTS["fail"] > SEVERITY_WEIGHTS["warn"]

    def test_all_check_weights_positive(self) -> None:
        for name, w in CHECK_WEIGHTS.items():
            assert w > 0, f"{name} weight must be positive"

    def test_default_check_weight_positive(self) -> None:
        assert DEFAULT_CHECK_WEIGHT > 0

    def test_max_violation_multiplier_at_least_two(self) -> None:
        assert MAX_VIOLATION_MULTIPLIER >= 2
