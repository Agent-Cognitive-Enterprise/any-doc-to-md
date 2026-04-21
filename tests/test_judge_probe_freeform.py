from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import fitz

from anydoc2md.judge_probe_freeform import (
    FreeformCaseScore,
    FreeformProbeVerdict,
    _parse_freeform_response,
)
from anydoc2md.judge_probe_freeform_case import build_freeform_probe_suite
from anydoc2md.judge_probe_freeform_runner import probe_freeform_model
from anydoc2md.judge_probe_models import ModelInfo


def test_build_freeform_probe_suite_writes_source_pdf_and_candidates(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)

    assert suite.source_pdf.exists()
    assert len(suite.cases) == 2
    assert {case.case_id for case in suite.cases} == {"candidate_a", "candidate_b"}
    assert (tmp_path / "candidate_a_staging" / "index.md").exists()
    assert (tmp_path / "candidate_b_staging" / "index.md").exists()
    assert (tmp_path / "candidate_b_staging" / "images" / "probe_red_square.png").exists()

    doc = fitz.open(suite.source_pdf)
    try:
        assert doc.page_count >= 7
    finally:
        doc.close()


def test_parse_freeform_response_scores_gold_issues_without_checklist(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    raw = """
    {
      "cases": {
        "candidate_a": [
          {
            "page": "1",
            "candidate_excerpt": "Warehouse / Handover / Packet",
            "why_wrong": "The title is split into fragments instead of one title.",
            "severity": "medium"
          },
          {
            "page": "2",
            "candidate_excerpt": "1. Seal the amber tote. 3. Attach the handover card. 2. Scan the dock marker.",
            "why_wrong": "The transfer steps are out of order.",
            "severity": "high"
          },
          {
            "page": "4",
            "candidate_excerpt": "The Shift Coverage Matrix became bullets.",
            "why_wrong": "The real table lost its columns.",
            "severity": "medium"
          },
          {
            "page": "4",
            "candidate_excerpt": "The Box 2 reminder about any red tag older than 12 hours is missing.",
            "why_wrong": "Material reminder text was omitted.",
            "severity": "medium"
          },
          {
            "page": "5",
            "candidate_excerpt": "images/missing-amber-square.png width=9999",
            "why_wrong": "The image reference is broken and the dimensions are implausible.",
            "severity": "high"
          }
        ],
        "candidate_b": [
          {
            "page": "7",
            "candidate_excerpt": "Figure 1. Amber square dock marker before sealing.",
            "why_wrong": "The caption is detached in the appendix instead of next to the image.",
            "severity": "medium"
          },
          {
            "page": "6",
            "candidate_excerpt": "Visitors must countersign the cold-room log.",
            "why_wrong": "That line is missing from the candidate.",
            "severity": "medium"
          }
        ]
      }
    }
    """

    verdict = _parse_freeform_response(raw, suite=suite, tokens_used=123)

    assert verdict.succeeded is True
    scores = {score.case_id: score for score in verdict.case_scores}
    assert scores["candidate_a"].matched_count == 5
    assert scores["candidate_a"].passed is True
    assert scores["candidate_b"].matched_count == 2
    assert scores["candidate_b"].passed is True


def test_probe_freeform_model_fails_when_case_misses_gate(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    verdict = FreeformProbeVerdict(
        case_scores=(
            FreeformCaseScore(
                case_id="candidate_a",
                matched_issue_ids=("fragmented_title", "step_order_broken"),
                false_positive_count=0,
                duplicate_count=0,
                min_expected_findings=5,
                max_false_positives=1,
                total_gold_issues=8,
            ),
            FreeformCaseScore(
                case_id="candidate_b",
                matched_issue_ids=("detached_caption", "missing_countersign_line"),
                false_positive_count=0,
                duplicate_count=0,
                min_expected_findings=2,
                max_false_positives=1,
                total_gold_issues=3,
            ),
        ),
        tokens_used=321,
    )

    with patch("anydoc2md.judge_probe_freeform_runner.run_freeform_probe", return_value=verdict):
        result = probe_freeform_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=60,
            suite=suite,
        )

    assert result.passed is False
    assert "candidate_a matched 2/8 gold issues" in result.reason


def test_probe_freeform_model_passes_when_all_cases_clear_gates(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    verdict = FreeformProbeVerdict(
        case_scores=(
            FreeformCaseScore(
                case_id="candidate_a",
                matched_issue_ids=(
                    "fragmented_title",
                    "repeated_running_header",
                    "step_order_broken",
                    "flattened_matrix",
                    "missing_red_tag_rule",
                ),
                false_positive_count=1,
                duplicate_count=0,
                min_expected_findings=5,
                max_false_positives=1,
                total_gold_issues=8,
            ),
            FreeformCaseScore(
                case_id="candidate_b",
                matched_issue_ids=("detached_caption", "missing_countersign_line"),
                false_positive_count=0,
                duplicate_count=0,
                min_expected_findings=2,
                max_false_positives=1,
                total_gold_issues=3,
            ),
        ),
        tokens_used=456,
    )

    with patch("anydoc2md.judge_probe_freeform_runner.run_freeform_probe", return_value=verdict):
        result = probe_freeform_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=60,
            suite=suite,
        )

    assert result.passed is True
    assert result.violations_count == 7
