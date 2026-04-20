"""
Weighted scoring for QA reports — lower score = better conversion.

Each check contributes:  CHECK_WEIGHTS[name] × SEVERITY_WEIGHTS[status] × violation_multiplier

violation_multiplier = max(1, min(len(details), MAX_VIOLATION_MULTIPLIER))
  → 0 details on a fail/warn → multiplier 1 (still penalised)
  → 10+ violations          → capped at MAX_VIOLATION_MULTIPLIER

Checks not in CHECK_WEIGHTS default to DEFAULT_CHECK_WEIGHT so new checks
added to checks.py are automatically included without a code change here.

Usage:
    from anydoc2md.output_qa.scoring import build_scorecard, rank_adapters

    report = run_all(staging_dir, source_path)
    card = build_scorecard(report, adapter_name="docling")
    print(card.total_score)            # lower is better
    ranked = rank_adapters([card_a, card_b, card_c])
    winner = ranked[0]
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from anydoc2md.output_qa.checks import CheckResult
from anydoc2md.output_qa.runner import QAReport

# ---------------------------------------------------------------------------
# Weight tables
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, float] = {
    "fail": 10.0,
    "warn":  2.0,
    "pass":  0.0,
}

# Per-check importance multipliers.
# Higher = more important.  Checks absent from this table use DEFAULT_CHECK_WEIGHT.
CHECK_WEIGHTS: dict[str, float] = {
    # Layer 1 — structural
    "no_double_bullets":          1.0,
    "numbered_list_sequential":   1.0,
    "heading_not_fragmented":     1.5,
    "caption_near_image":         3.0,
    "box_title_precedes_content": 2.0,
    "image_size_plausible":       0.5,
    "no_repeated_headings":       1.5,
    "images_locally_resolvable":  5.0,   # broken refs are a hard signal
    # Layer 2 — fidelity
    "image_count_match":          3.0,
    "text_coverage":              5.0,   # missing text = broken conversion
}

DEFAULT_CHECK_WEIGHT: float = 1.0
MAX_VIOLATION_MULTIPLIER: int = 10


# ---------------------------------------------------------------------------
# ScoreCard
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreCard:
    """Scoring result for one adapter's conversion of one document."""

    adapter_name: str
    total_score: float              # lower = better; 0.0 = perfect
    check_scores: dict[str, float]  # per-check breakdown
    fail_count: int
    warn_count: int
    pass_count: int

    @property
    def check_count(self) -> int:
        return self.fail_count + self.warn_count + self.pass_count

    def to_dict(self) -> dict:
        return {
            "adapter_name": self.adapter_name,
            "total_score": self.total_score,
            "check_scores": self.check_scores,
            "check_count": self.check_count,
            "fail_count": self.fail_count,
            "warn_count": self.warn_count,
            "pass_count": self.pass_count,
        }


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_check(check: CheckResult) -> float:
    """
    Return the penalty score for one CheckResult.

    Score = check_weight × severity_weight × violation_multiplier

    violation_multiplier is 1 when details is empty (still penalised for the
    status itself), or min(len(details), MAX_VIOLATION_MULTIPLIER) otherwise.
    """
    severity = SEVERITY_WEIGHTS.get(check.status, 0.0)
    if severity == 0.0:
        return 0.0

    weight = CHECK_WEIGHTS.get(check.name, DEFAULT_CHECK_WEIGHT)
    multiplier = max(1, min(len(check.details), MAX_VIOLATION_MULTIPLIER))
    return weight * severity * multiplier


def build_scorecard(report: QAReport, adapter_name: str) -> ScoreCard:
    """
    Build a ScoreCard from a QAReport for the named adapter.

    Args:
        report:       Output of output_qa.runner.run_all().
        adapter_name: Short name of the converter (e.g. "docling").

    Returns:
        ScoreCard with total_score and per-check breakdown.
    """
    per_check: dict[str, float] = {}
    fail_count = warn_count = pass_count = 0

    for check in report.checks:
        per_check[check.name] = score_check(check)
        if check.status == "fail":
            fail_count += 1
        elif check.status == "warn":
            warn_count += 1
        else:
            pass_count += 1

    return ScoreCard(
        adapter_name=adapter_name,
        total_score=sum(per_check.values()),
        check_scores=per_check,
        fail_count=fail_count,
        warn_count=warn_count,
        pass_count=pass_count,
    )


def rank_adapters(scorecards: list[ScoreCard]) -> list[ScoreCard]:
    """
    Return scorecards sorted by total_score ascending (best first).

    Ties are broken alphabetically by adapter_name for determinism.
    """
    return sorted(scorecards, key=lambda c: (c.total_score, c.adapter_name))
