from __future__ import annotations

import json
from dataclasses import replace

from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings, RepairDraft
from anydoc2md.paragraph_repair.quality import (
    accept_repair,
    normalized_content_fingerprint,
    score_paragraph_quality,
)
from anydoc2md.paragraph_repair.repairer import repair_blocks


def test_clear_row_sliced_repair_is_accepted() -> None:
    original = _row_sliced_fixture()
    draft = _draft(original)

    decision = accept_repair(original, draft)

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.row_sliced_evidence is True
    assert decision.content_preserved is True
    assert decision.structural_counts_preserved is True
    assert decision.merge_group_count > 0
    assert decision.after_score > decision.before_score
    assert decision.quality_delta > ParagraphRepairSettings().min_quality_delta
    assert json.loads(json.dumps(decision.to_dict())) == decision.to_dict()


def test_score_rewards_less_fragmented_candidate() -> None:
    original = _row_sliced_fixture()
    draft = _draft(original)

    before = score_paragraph_quality(split_markdown_blocks(original))
    after = score_paragraph_quality(split_markdown_blocks(draft.text))

    assert after > before


def test_normal_prose_without_merges_is_rejected() -> None:
    original = _normal_prose_fixture()
    draft = _draft(original)

    decision = accept_repair(original, draft)

    assert decision.accepted is False
    assert decision.reason == "no_merge_groups"
    assert decision.merge_group_count == 0


def test_paragraph_count_change_without_row_sliced_evidence_is_rejected() -> None:
    original = _normal_prose_fixture()
    candidate = original.replace("\n\n", " ", 1)
    draft = RepairDraft(
        text=candidate,
        merge_group_count=1,
        original_paragraph_count=4,
        repaired_paragraph_count=3,
        content_preserved=True,
    )

    decision = accept_repair(original, draft)

    assert decision.accepted is False
    assert decision.reason == "no_row_sliced_evidence"
    assert decision.row_sliced_evidence is False


def test_short_document_with_real_merge_is_rejected_by_document_detector() -> None:
    original = "\n\n".join(
        [
            "The operator reported that the pump",
            "continued cycling while the backup",
            "generator switched load and the",
            "manual log showed brief pressure",
            "drops near the east manifold",
            "during the storm.",
        ]
    ) + "\n"
    draft = _draft(original)

    decision = accept_repair(original, draft)

    assert draft.merge_group_count == 1
    assert decision.accepted is False
    assert decision.reason == "no_row_sliced_evidence"
    assert decision.signals["detection_reason"] == "too_few_prose_blocks"


def test_candidate_with_dropped_word_is_rejected() -> None:
    original = _row_sliced_fixture()
    draft = _draft(original)
    candidate = draft.text.replace("backup ", "", 1)
    damaged_draft = replace(draft, text=candidate)

    decision = accept_repair(original, damaged_draft)

    assert decision.accepted is False
    assert decision.reason == "content_not_preserved"
    assert decision.content_preserved is False


def test_candidate_damaging_structural_counts_is_rejected() -> None:
    structural = (
        "\n\n```text\ncode sample\n```\n"
        "\n| Time | Reading |\n| --- | --- |\n| 10:00 | Low |\n"
        "\n- Inspect actuator\n- Photograph panel labels\n"
    )
    original = _row_sliced_fixture() + structural
    draft = _draft(original)
    candidate = draft.text.replace(
        "- Inspect actuator\n- Photograph panel labels\n",
        "Inspect actuator\nPhotograph panel labels\n",
    )
    damaged_draft = replace(draft, text=candidate)

    decision = accept_repair(original, damaged_draft)

    assert decision.accepted is False
    assert decision.reason == "structural_counts_changed"
    assert decision.structural_counts_preserved is False


def test_tiny_improvement_below_threshold_is_rejected() -> None:
    original = _row_sliced_fixture()
    settings = ParagraphRepairSettings(min_quality_delta=10_000.0)
    draft = _draft(original, settings)

    decision = accept_repair(original, draft, settings)

    assert decision.accepted is False
    assert decision.reason == "quality_delta_too_small"
    assert 0 < decision.quality_delta < settings.min_quality_delta


def test_disabled_settings_reject_with_clear_reason() -> None:
    original = _row_sliced_fixture()
    draft = _draft(original)

    decision = accept_repair(
        original,
        draft,
        ParagraphRepairSettings(enabled=False),
    )

    assert decision.accepted is False
    assert decision.reason == "disabled"


def test_normalized_content_fingerprint_ignores_whitespace_only() -> None:
    assert normalized_content_fingerprint("well-\n\nknown") == (
        normalized_content_fingerprint("well-known")
    )
    assert normalized_content_fingerprint("state-of-the-art") != (
        normalized_content_fingerprint("state-of-theart")
    )


def _draft(
    md_text: str,
    settings: ParagraphRepairSettings | None = None,
):
    return repair_blocks(split_markdown_blocks(md_text), settings)


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


def _normal_prose_fixture() -> str:
    rows = [
        "The pump started after the alarm and stabilized within five minutes.",
        "The operator reviewed the sensor logs and found no missing readings.",
        "The maintenance lead scheduled a follow up inspection for the morning.",
        "The final note records that the intake remained open during the test.",
    ]
    return "\n\n".join(rows) + "\n"
