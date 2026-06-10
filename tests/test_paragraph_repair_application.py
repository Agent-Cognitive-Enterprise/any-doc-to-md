from __future__ import annotations

import json

from anydoc2md.paragraph_repair.application import (
    repair_markdown_paragraph_continuity,
)
from anydoc2md.paragraph_repair.model import (
    ParagraphRepairResult,
    ParagraphRepairSettings,
)


def test_clear_row_sliced_document_is_repaired() -> None:
    original = _row_sliced_fixture()

    result = repair_markdown_paragraph_continuity(original)

    assert isinstance(result, ParagraphRepairResult)
    assert result.text != original
    assert result.report.attempted is True
    assert result.report.accepted is True
    assert result.report.reason == "accepted"
    assert result.report.merge_group_count > 0
    assert (
        result.report.repaired_paragraph_count
        < result.report.original_paragraph_count
    )
    assert result.report.after_score > result.report.before_score


def test_realistic_short_row_sliced_document_is_repaired() -> None:
    original = _short_row_sliced_fixture()

    result = repair_markdown_paragraph_continuity(original)

    assert result.text != original
    assert result.report.accepted is True
    assert result.report.reason == "accepted"
    assert result.report.original_paragraph_count == 13
    assert result.report.repaired_paragraph_count == 2
    assert result.report.signals["detection_reason"] == "row_sliced_prose_detected"
    assert (
        "The inspection team arrived at the north intake after the first alarm"
        in result.text
    )


def test_normal_prose_is_returned_unchanged() -> None:
    original = _normal_prose_fixture()

    result = repair_markdown_paragraph_continuity(original)

    assert result.text == original
    assert result.report.attempted is True
    assert result.report.accepted is False
    assert result.report.reason == "no_merge_groups"
    assert (
        result.report.repaired_paragraph_count
        == result.report.original_paragraph_count
    )


def test_short_row_sliced_document_is_rejected_by_document_detector() -> None:
    original = (
        "\n\n".join(
            [
                "The inspection team arrived at the north intake",
                "after the first alarm and found that the overflow",
                "channel was carrying shallow water across the grated",
                "walkway while the upstream valve remained partially",
                "open without recording a stable pressure reading.",
                "A short unrelated closing note that ends cleanly.",
            ]
        )
        + "\n"
    )

    result = repair_markdown_paragraph_continuity(original)

    # The repairer finds a merge run, but the conservative document detector
    # rejects a sub-`min_paragraphs` document, so the original is preserved.
    assert result.report.merge_group_count > 0
    assert result.text == original
    assert result.report.accepted is False
    assert result.report.reason == "no_row_sliced_evidence"
    assert result.report.signals["detection_reason"] == "too_few_prose_blocks"


def test_empty_input_is_safe() -> None:
    result = repair_markdown_paragraph_continuity("")

    assert result.text == ""
    assert result.report.attempted is True
    assert result.report.accepted is False
    assert result.report.original_paragraph_count == 0
    assert result.report.merge_group_count == 0


def test_whitespace_only_input_is_returned_unchanged() -> None:
    original = "   \n\n\t\n"

    result = repair_markdown_paragraph_continuity(original)

    assert result.text == original
    assert result.report.accepted is False
    assert result.report.original_paragraph_count == 0


def test_disabled_settings_return_original_and_not_attempted() -> None:
    original = _row_sliced_fixture()

    result = repair_markdown_paragraph_continuity(
        original, ParagraphRepairSettings(enabled=False)
    )

    assert result.text == original
    assert result.report.attempted is False
    assert result.report.accepted is False
    assert result.report.reason == "disabled"
    # Disabled mode must not draft merges or leak candidate evidence.
    assert result.report.merge_group_count == 0
    assert result.report.examples == []
    assert result.report.before_score == 0.0
    assert result.report.after_score == 0.0
    assert result.report.signals == {}
    assert result.report.original_paragraph_count > 0
    assert (
        result.report.repaired_paragraph_count
        == result.report.original_paragraph_count
    )


def test_result_to_dict_is_json_serializable() -> None:
    result = repair_markdown_paragraph_continuity(_row_sliced_fixture())

    payload = result.to_dict()

    assert payload["report"]["accepted"] is True
    assert json.loads(json.dumps(payload)) == payload


def test_repeated_calls_are_deterministic() -> None:
    original = _row_sliced_fixture()

    first = repair_markdown_paragraph_continuity(original)
    second = repair_markdown_paragraph_continuity(original)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_examples_are_bounded_by_settings() -> None:
    settings = ParagraphRepairSettings(max_examples=1, max_example_chars=10)

    result = repair_markdown_paragraph_continuity(_row_sliced_fixture(), settings)

    assert len(result.report.examples) <= 1
    assert all(len(example) <= 10 for example in result.report.examples)


def test_package_exports_orchestrator() -> None:
    import anydoc2md.paragraph_repair as paragraph_repair

    assert (
        paragraph_repair.repair_markdown_paragraph_continuity
        is repair_markdown_paragraph_continuity
    )


def _row_sliced_fixture() -> str:
    rows = [
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
    return "\n\n".join(rows) + "\n"


def _short_row_sliced_fixture() -> str:
    rows = [
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
    return "\n\n".join(rows) + "\n"


def _normal_prose_fixture() -> str:
    rows = [
        "The pump started after the alarm and stabilized within five minutes.",
        "The operator reviewed the sensor logs and found no missing readings.",
        "The maintenance lead scheduled a follow up inspection for the morning.",
        "The final note records that the intake remained open during the test.",
    ]
    return "\n\n".join(rows) + "\n"
