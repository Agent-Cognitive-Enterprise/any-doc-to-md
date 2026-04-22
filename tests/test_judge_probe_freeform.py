from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import fitz

from anydoc2md.judge_probe_freeform import (
    FreeformCaseScore,
    FreeformProbeVerdict,
    _parse_freeform_case_response,
)
from anydoc2md.judge_probe_freeform_case import build_freeform_probe_suite
from anydoc2md.judge_probe_freeform_runner import probe_freeform_model
from anydoc2md.judge_probe_models import ModelInfo


def test_build_freeform_probe_suite_writes_source_pdf_and_candidates(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)

    assert suite.source_pdf.exists()
    assert len(suite.cases) == 1
    assert {case.case_id for case in suite.cases} == {"candidate_a"}
    assert (tmp_path / "candidate_a_staging" / "index.md").exists()

    doc = fitz.open(suite.source_pdf)
    try:
        assert doc.page_count >= 7
    finally:
        doc.close()


def test_parse_freeform_case_response_scores_gold_issues_without_checklist(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    candidate_a_raw = """
    {
      "issues": [
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
        }
      ]
    }
    """

    candidate_a_score, candidate_a_error = _parse_freeform_case_response(
        candidate_a_raw,
        case=suite.cases[0],
        tokens_used=123,
    )

    assert candidate_a_error == ""
    assert candidate_a_score is not None
    assert candidate_a_score.matched_count == 3
    assert candidate_a_score.passed is True


def test_parse_freeform_case_response_accepts_single_issue_object_field(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    raw = """
    {
      "issue": {
        "page": "1",
        "candidate_excerpt": "Warehouse / Handover / Packet",
        "why_wrong": "The title is split into fragments instead of one title.",
        "severity": "medium"
      }
    }
    """

    score, error = _parse_freeform_case_response(raw, case=suite.cases[0], tokens_used=12)

    assert error == ""
    assert score is not None
    assert score.matched_count == 1
    assert score.passed is False


def test_parse_freeform_case_response_recovers_jsonish_issue_blocks(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    raw = (
        '{"issues": [{"page": "1", "candidate_excerpt": "Warehouse / Handover / Packet", '
        '"why_wrong": "The title is split into fragments instead of one title.", '
        '"severity": "medium"} {"page": "2", "candidate_excerpt": '
        '"1. Seal the amber tote. 3. Attach the handover card. 2. Scan the dock marker.", '
        '"why_wrong": "The transfer steps are out of order.", "severity": "high"} '
        '{"page": "4", "candidate_excerpt": "The Shift Coverage Matrix became bullets.", '
        '"why_wrong": "The real table lost its columns.", "severity": "medium"}]}'
    )

    score, error = _parse_freeform_case_response(raw, case=suite.cases[0], tokens_used=55)

    assert error == ""
    assert score is not None
    assert score.matched_count == 3
    assert score.passed is True


def test_probe_freeform_model_fails_when_case_misses_gate(tmp_path: Path) -> None:
    suite = build_freeform_probe_suite(tmp_path)
    verdict = FreeformProbeVerdict(
        case_scores=(
            FreeformCaseScore(
                case_id="candidate_a",
                matched_issue_ids=("fragmented_title", "step_order_broken"),
                false_positive_count=0,
                duplicate_count=0,
                min_expected_findings=3,
                max_false_positives=2,
                total_gold_issues=8,
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
                ),
                false_positive_count=1,
                duplicate_count=0,
                min_expected_findings=3,
                max_false_positives=2,
                total_gold_issues=8,
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
    assert result.violations_count == 3
