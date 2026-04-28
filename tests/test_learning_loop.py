"""Tests for the agent-in-loop retry cycle (learning_loop.py)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from anydoc2md.learning_loop import (
    MAX_LOOP_ATTEMPTS,
    LearningLoopResult,
    _has_major_findings,
    _stage_scaffolds,
    _write_escalation,
    run_learning_loop,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal mock TournamentResult objects
# ---------------------------------------------------------------------------

def _mock_verdict(*, major: bool = False) -> MagicMock:
    verdict = MagicMock()
    violation = MagicMock()
    violation.severity = "major" if major else "minor"
    violation.to_dict.return_value = {"type": "stub", "severity": violation.severity}
    verdict.violations = [violation] if major else []
    return verdict


def _mock_plan() -> MagicMock:
    plan = MagicMock()
    plan.to_dict.return_value = {
        "target_adapter": "inhouse",
        "tasks": [
            {
                "violation_type": "caption_detachment",
                "severity": "major",
                "evidence": "Caption far from image.",
                "root_cause": "",
                "suggested_fix": "",
                "suggested_fix_area": "",
                "pages": [],
                "target_adapter": "inhouse",
                "compare_against": "docling",
                "suggested_test": "",
            }
        ],
    }
    return plan


def _mock_result(*, major: bool = False, with_plan: bool = True) -> MagicMock:
    result = MagicMock()
    result.judge_verdict = _mock_verdict(major=major)
    result.remediation_plan = _mock_plan() if (major and with_plan) else None
    result.winner = "inhouse"
    result.audit_mode = "auto"
    result.to_dict.return_value = {}
    return result


# ---------------------------------------------------------------------------
# _has_major_findings
# ---------------------------------------------------------------------------

def test_has_major_findings_none_verdict():
    assert _has_major_findings(None) is False


def test_has_major_findings_no_violations():
    verdict = MagicMock()
    verdict.violations = []
    assert _has_major_findings(verdict) is False


def test_has_major_findings_minor_only():
    assert _has_major_findings(_mock_verdict(major=False)) is False


def test_has_major_findings_major():
    assert _has_major_findings(_mock_verdict(major=True)) is True


# ---------------------------------------------------------------------------
# _stage_scaffolds
# ---------------------------------------------------------------------------

def test_stage_scaffolds_copies_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "my_doc.py").write_text("# qa ext\n", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()

    _stage_scaffolds({"qa_extension": src / "my_doc.py"}, staging)
    assert (staging / "qa_extension.py").read_text(encoding="utf-8") == "# qa ext\n"


def test_stage_scaffolds_ignores_unknown_keys(tmp_path: Path) -> None:
    src = tmp_path / "src" / "doc.py"
    src.parent.mkdir()
    src.write_text("x\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    _stage_scaffolds({"unknown_key": src}, staging)
    assert not any(staging.iterdir())


# ---------------------------------------------------------------------------
# _write_escalation
# ---------------------------------------------------------------------------

def test_write_escalation_creates_json(tmp_path: Path) -> None:
    path = _write_escalation(
        anydoc2md_dir=tmp_path,
        doc_key="report",
        source_path=Path("/docs/report.pdf"),
        attempts=3,
        final_result=_mock_result(major=True),
    )
    assert path == tmp_path / "escalations" / "report.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["doc_key"] == "report"
    assert record["attempts"] == 3
    assert record["escalated_at"]
    assert "Human review required" in record["message"]


def test_write_escalation_includes_violations(tmp_path: Path) -> None:
    result = _mock_result(major=True)
    violation = MagicMock()
    violation.severity = "major"
    violation.to_dict.return_value = {"type": "caption_detachment", "severity": "major"}
    result.judge_verdict.violations = [violation]
    path = _write_escalation(
        anydoc2md_dir=tmp_path,
        doc_key="doc",
        source_path=Path("/x.pdf"),
        attempts=3,
        final_result=result,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["violations"][0]["type"] == "caption_detachment"


# ---------------------------------------------------------------------------
# run_learning_loop — clean pass on first attempt
# ---------------------------------------------------------------------------

def test_loop_accepts_clean_result_immediately(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    anydoc2md_dir = tmp_path / ".any-doc-to-md"

    clean_result = _mock_result(major=False)

    with patch("anydoc2md.learning_loop.run_full_tournament", return_value=clean_result) as mock_run:
        loop_result = run_learning_loop(
            Path("/doc.pdf"), staging, anydoc2md_dir, "doc",
        )

    assert loop_result.attempts == 1
    assert loop_result.escalated is False
    assert loop_result.escalation_path is None
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# run_learning_loop — major findings trigger scaffold generation and retry
# ---------------------------------------------------------------------------

def test_loop_retries_after_major_findings(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    anydoc2md_dir = tmp_path / ".any-doc-to-md"

    # First attempt: major findings. Second attempt: clean.
    major_result = _mock_result(major=True)
    clean_result = _mock_result(major=False)

    with patch("anydoc2md.learning_loop.run_full_tournament",
               side_effect=[major_result, clean_result]) as mock_run:
        loop_result = run_learning_loop(
            Path("/doc.pdf"), staging, anydoc2md_dir, "doc",
        )

    assert loop_result.attempts == 2
    assert loop_result.escalated is False
    assert mock_run.call_count == 2


def test_loop_generates_scaffolds_after_major_findings(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    anydoc2md_dir = tmp_path / ".any-doc-to-md"

    major_result = _mock_result(major=True)
    clean_result = _mock_result(major=False)

    with patch("anydoc2md.learning_loop.run_full_tournament",
               side_effect=[major_result, clean_result]):
        loop_result = run_learning_loop(
            Path("/doc.pdf"), staging, anydoc2md_dir, "doc",
        )

    assert len(loop_result.scaffold_paths) > 0
    # Scaffolds are staged into staging_root for extension loader pickup
    assert (staging / "qa_extension.py").exists()


# ---------------------------------------------------------------------------
# run_learning_loop — escalation after max attempts
# ---------------------------------------------------------------------------

def test_loop_escalates_after_max_attempts(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    anydoc2md_dir = tmp_path / ".any-doc-to-md"

    always_major = _mock_result(major=True)

    with patch("anydoc2md.learning_loop.run_full_tournament",
               return_value=always_major) as mock_run:
        loop_result = run_learning_loop(
            Path("/doc.pdf"), staging, anydoc2md_dir, "doc",
            max_attempts=3,
        )

    assert loop_result.attempts == 3
    assert loop_result.escalated is True
    assert loop_result.escalation_path is not None
    assert loop_result.escalation_path.exists()
    assert mock_run.call_count == 3


def test_loop_escalation_record_has_correct_content(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    anydoc2md_dir = tmp_path / ".any-doc-to-md"

    with patch("anydoc2md.learning_loop.run_full_tournament",
               return_value=_mock_result(major=True)):
        loop_result = run_learning_loop(
            Path("/report.pdf"), staging, anydoc2md_dir, "report",
            max_attempts=2,
        )

    record = json.loads(loop_result.escalation_path.read_text(encoding="utf-8"))
    assert record["doc_key"] == "report"
    assert record["attempts"] == 2


def test_loop_respects_custom_max_attempts(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()

    with patch("anydoc2md.learning_loop.run_full_tournament",
               return_value=_mock_result(major=True)) as mock_run:
        run_learning_loop(
            Path("/doc.pdf"), staging, tmp_path / ".adtm", "doc",
            max_attempts=1,
        )

    assert mock_run.call_count == 1
