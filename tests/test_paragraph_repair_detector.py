from __future__ import annotations

import pytest

from anydoc2md.paragraph_repair.detector import (
    compute_fragmentation_signals,
    looks_like_continuation,
    looks_row_sliced,
)
from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings


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
            "generator switched load.",
            "Because the site has limited lighting",
            "the team marked the affected panels with tape",
            "and postponed nonessential work until daylight.",
            "A follow up review should compare the sensor",
            "timestamps with pump starts and check whether",
            "the valve actuator is drifting under load",
            "before the next forecasted rain event.",
            "The maintenance lead asked that the morning crew",
            "verify the bypass pump before reopening the intake",
            "and record any new vibration near the manifold.",
        ]
    )


def _decision(md_text: str, settings: ParagraphRepairSettings | None = None):
    return looks_row_sliced(split_markdown_blocks(md_text), settings)


def _signals(md_text: str):
    return compute_fragmentation_signals(split_markdown_blocks(md_text))


def test_row_sliced_pdf_like_prose_is_detected_with_default_settings() -> None:
    decision = _decision(_row_sliced_fixture())

    assert decision.detected is True
    assert decision.reason == "row_sliced_prose_detected"
    assert decision.signals.prose_block_count == 22
    assert decision.signals.short_ratio == 1.0
    assert decision.signals.no_terminal_ratio == pytest.approx(17 / 22)
    assert decision.signals.lowercase_start_ratio == 1.0
    assert decision.signals.continuation_pair_ratio == pytest.approx(17 / 21)
    assert decision.signals.qualifying_continuation_run_count == 3
    assert decision.signals.longest_continuation_run == 7


def test_normal_multi_paragraph_prose_is_not_detected() -> None:
    md = "\n\n".join(
        [
            "The pump started after the alarm and then stabilized within five minutes.",
            "The operator reviewed the sensor logs and found no missing readings.",
            "The maintenance lead scheduled a follow up inspection for the morning.",
            "The final note records that the intake remained open during the test.",
        ]
    )

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.longest_continuation_run == 0


def test_short_paragraphs_alone_do_not_trigger_detection() -> None:
    md = "\n\n".join(f"Station note {index}" for index in range(25))
    settings = ParagraphRepairSettings(min_paragraphs=20)

    decision = _decision(md, settings)

    assert decision.detected is False
    assert decision.signals.short_ratio == 1.0
    assert decision.signals.no_terminal_ratio == 1.0
    assert decision.signals.continuation_pair_ratio == 0.0
    assert decision.reason == "continuation_pair_ratio_below_threshold"


def test_lowercase_poetry_like_short_lines_do_not_trigger_detection() -> None:
    md = "\n\n".join(
        [
            "river stone",
            "under glass",
            "small hours",
            "without names",
            "in the rain",
        ]
        * 5
    )

    decision = _decision(md)

    assert decision.detected is False
    assert decision.signals.short_ratio == 1.0
    assert decision.signals.continuation_pair_ratio == 0.0
    assert decision.reason == "continuation_pair_ratio_below_threshold"


def test_bullet_heavy_notes_are_not_detected() -> None:
    md = "\n".join(f"- Inspect item {index}" for index in range(25))

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.prose_block_count == 0
    assert decision.signals.structural_block_count == 1


def test_table_like_rows_are_not_detected() -> None:
    md = "\n".join(
        [
            "| Time | Reading |",
            "| --- | --- |",
            "| 10:00 | Low |",
            "| 10:05 | Stable |",
            "| 10:10 | Stable |",
        ]
    )

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.prose_block_count == 0
    assert decision.signals.structural_block_count == 1


def test_heading_heavy_outline_is_not_detected() -> None:
    md = "\n\n".join(
        f"## Step {index}\n\nOwner {index} confirmed the reading."
        for index in range(12)
    )

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.structural_block_count == 12
    assert decision.signals.prose_block_count == 12
    assert decision.signals.longest_continuation_run == 0


def test_short_document_below_minimum_is_not_detected_even_with_run_evidence() -> None:
    md = "\n\n".join(
        [
            "The operator reported that the same pattern",
            "had appeared during the previous storm and that",
            "the manual log showed brief pressure drops",
            "near the east manifold whenever the backup",
            "generator switched load.",
        ]
    )

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.longest_continuation_run >= 4


def test_mixed_document_reports_run_level_evidence_without_document_detection() -> None:
    normal = [
        f"Section {index} is complete and includes a normal sentence."
        for index in range(18)
    ]
    sliced = [
        "The operator reported that the same pattern",
        "had appeared during the previous storm and that",
        "the manual log showed brief pressure drops",
        "near the east manifold whenever the backup",
        "generator switched load.",
    ]
    md = "\n\n".join(normal[:9] + sliced + normal[9:])

    decision = _decision(md)

    assert decision.detected is False
    assert decision.signals.prose_block_count >= 20
    assert decision.signals.longest_continuation_run >= 4


def test_continuation_pair_heuristic_requires_more_than_short_lines() -> None:
    assert looks_like_continuation("Alpha beta", "Gamma delta") is False
    assert looks_like_continuation(
        "the pump continued cycling",
        "every few minutes",
    ) is True
    assert looks_like_continuation(
        "The pump stopped.",
        "the operator checked it",
    ) is False
    assert looks_like_continuation(
        "the pump continued cycling,",
        "- every few minutes while the backup pump stayed online",
    ) is False


def test_detector_is_disabled_by_settings() -> None:
    decision = _decision(
        _row_sliced_fixture(),
        ParagraphRepairSettings(enabled=False),
    )

    assert decision.detected is False
    assert decision.reason == "disabled"


def test_empty_and_whitespace_documents_are_not_detected() -> None:
    assert _decision("").reason == "too_few_prose_blocks"
    assert _decision(" \n\t\n").reason == "too_few_prose_blocks"


def test_structural_only_document_is_not_detected() -> None:
    md = "# Report\n\n- Item one\n- Item two\n\n| A | B |\n| --- | --- |\n"

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.structural_block_count == 3


def test_structure_ratio_ignores_blank_separators() -> None:
    md = "# First\n\nParagraph one.\n\n# Second\n\nParagraph two.\n"

    signals = _signals(md)

    assert signals.prose_block_count == 2
    assert signals.structural_block_count == 2
    assert signals.blank_block_count > 0
    assert signals.structure_ratio == 0.5


def test_threshold_settings_drive_short_ratio_gate() -> None:
    decision = _decision(
        _row_sliced_fixture(),
        ParagraphRepairSettings(short_prose_chars=20),
    )

    assert decision.detected is False
    assert decision.reason == "short_ratio_below_threshold"


def test_threshold_settings_drive_lowercase_gate() -> None:
    decision = _decision(
        _row_sliced_fixture(),
        ParagraphRepairSettings(min_lowercase_start_ratio=1.1),
    )

    assert decision.detected is False
    assert decision.reason == "lowercase_start_ratio_below_threshold"


def test_threshold_settings_drive_continuation_length_gate() -> None:
    decision = _decision(
        _row_sliced_fixture(),
        ParagraphRepairSettings(min_continuation_chars=500),
    )

    assert decision.detected is False
    assert decision.reason == "continuation_pair_ratio_below_threshold"


def test_threshold_settings_drive_continuation_run_gate() -> None:
    decision = _decision(
        _row_sliced_fixture(),
        ParagraphRepairSettings(min_continuation_run_blocks=99),
    )

    assert decision.detected is False
    assert decision.reason == "no_qualifying_continuation_run"


def test_threshold_settings_drive_structure_ratio_gate() -> None:
    md = "# Report\n\n" + _row_sliced_fixture()

    decision = _decision(md, ParagraphRepairSettings(max_structure_ratio=0.0))

    assert decision.detected is False
    assert decision.reason == "structure_ratio_above_threshold"


def test_min_paragraphs_zero_does_not_force_empty_document_detection() -> None:
    decision = _decision("", ParagraphRepairSettings(min_paragraphs=0))

    assert decision.detected is False
    assert decision.reason == "short_ratio_below_threshold"


def test_soft_line_break_rows_are_currently_one_markdown_paragraph() -> None:
    md = "\n".join(_row_sliced_fixture().split("\n\n"))

    decision = _decision(md)

    assert decision.detected is False
    assert decision.reason == "too_few_prose_blocks"
    assert decision.signals.prose_block_count == 1


def test_signals_to_dict_is_json_friendly() -> None:
    signals = _signals("The pump continued cycling\n\nevery few minutes\n")

    payload = signals.to_dict()

    assert payload["prose_block_count"] == 2
    assert payload["continuation_pair_ratio"] == 1.0
    assert "has_run_level_evidence" not in payload


def test_detection_decision_to_dict_is_json_friendly() -> None:
    decision = _decision("The pump continued cycling\n\nevery few minutes\n")

    payload = decision.to_dict()

    assert payload["detected"] is False
    assert payload["reason"] == "too_few_prose_blocks"
    assert payload["signals"]["prose_block_count"] == 2
