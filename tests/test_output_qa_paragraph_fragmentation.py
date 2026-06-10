from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md.output_qa.checks import CheckResult, check_paragraph_not_row_sliced
from anydoc2md.output_qa.runner import run_all
from anydoc2md.output_qa.scoring import (
    CHECK_WEIGHTS,
    DOCUMENT_LEVEL_CHECK_MULTIPLIERS,
    SEVERITY_WEIGHTS,
    build_scorecard,
    score_check,
)
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings


def test_row_sliced_prose_warns_with_bounded_signal_details() -> None:
    result = check_paragraph_not_row_sliced(_row_sliced_fixture())

    assert result.name == "paragraph_not_row_sliced"
    assert result.layer == 1
    assert result.status == "warn"
    assert len(result.details) <= 2
    assert result.details[0].startswith("signals: ")
    assert "prose_blocks=" in result.details[0]
    assert "longest_continuation_run=" in result.details[0]
    assert "inspection team" not in "\n".join(result.details)


def test_normal_prose_passes() -> None:
    md = "\n\n".join(
        [
            "The pump started after the alarm and stabilized within five minutes.",
            "The operator reviewed the sensor logs and found no missing readings.",
            "The maintenance lead scheduled a follow up inspection for the morning.",
        ]
    )

    result = check_paragraph_not_row_sliced(md)

    assert result.status == "pass"
    assert result.details == []


def test_settings_can_tighten_detection_threshold() -> None:
    result = check_paragraph_not_row_sliced(
        _row_sliced_fixture(),
        ParagraphRepairSettings(min_paragraphs=99),
    )

    assert result.status == "pass"


def test_warning_is_independent_of_repair_mode() -> None:
    md = _row_sliced_fixture()

    # The tournament always calls the check with defaults (this is the pipeline
    # path: run_all -> check_paragraph_not_row_sliced(md_text)), so disabling
    # paragraph repair never silences the warning — fragmentation is reported,
    # just not auto-fixed.
    assert check_paragraph_not_row_sliced(md).status == "warn"

    # Only an explicit disabled-detector override suppresses it, and the
    # pipeline deliberately never passes one. This pins that the QA warning is
    # not gated on whether repair ran.
    disabled = check_paragraph_not_row_sliced(
        md, ParagraphRepairSettings(enabled=False)
    )
    assert disabled.status == "pass"


@pytest.mark.parametrize(
    "md",
    [
        "- Inspect item one\n- Inspect item two\n- Inspect item three\n",
        "| Time | Reading |\n| --- | --- |\n| 10:00 | Stable |\n",
        "```text\nThe pump continued cycling\nwithout a stable reading\n```\n",
    ],
)
def test_structural_markdown_passes(md: str) -> None:
    result = check_paragraph_not_row_sliced(md)

    assert result.status == "pass"


def test_run_all_includes_paragraph_fragmentation_check(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.md").write_text(_row_sliced_fixture(), encoding="utf-8")

    report = run_all(staging)

    checks = {check.name: check for check in report.checks}
    assert checks["paragraph_not_row_sliced"].status == "warn"
    assert report.passed is True


def test_fragmentation_warning_score_is_document_level_not_detail_count() -> None:
    warning = CheckResult(
        "paragraph_not_row_sliced",
        1,
        "warn",
        "Likely row-sliced paragraph fragmentation detected.",
        ["signals: ...", "sample_nonterminal_prose_lines=1,3,5"],
    )
    noisy_warning = CheckResult(
        "paragraph_not_row_sliced",
        1,
        "warn",
        "Likely row-sliced paragraph fragmentation detected.",
        [f"diagnostic {index}" for index in range(10)],
    )

    score = score_check(warning)
    assert score == pytest.approx(score_check(noisy_warning))
    assert score == pytest.approx(_paragraph_fragmentation_score())
    assert score == pytest.approx(6.0)


def test_scorecard_includes_fragmentation_warning_score(tmp_path: Path) -> None:
    card = build_scorecard(
        run_all(_staging_with_text(tmp_path, _row_sliced_fixture())),
        "fragmented",
    )

    assert card.check_scores["paragraph_not_row_sliced"] == pytest.approx(
        _paragraph_fragmentation_score()
    )
    assert card.check_scores["paragraph_not_row_sliced"] == pytest.approx(6.0)


def _staging_with_text(tmp_path: Path, md_text: str) -> Path:
    path = tmp_path / "scorecard-staging"
    path.mkdir()
    (path / "index.md").write_text(md_text, encoding="utf-8")
    return path


def _paragraph_fragmentation_score() -> float:
    return (
        CHECK_WEIGHTS["paragraph_not_row_sliced"]
        * SEVERITY_WEIGHTS["warn"]
        * DOCUMENT_LEVEL_CHECK_MULTIPLIERS["paragraph_not_row_sliced"]
    )


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
