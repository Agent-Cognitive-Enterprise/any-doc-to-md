from __future__ import annotations

from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings
from anydoc2md.paragraph_repair.repairer import (
    _content_preserved,
    pair_is_continuation,
    repair_blocks,
)


def test_content_preserved_guard_detects_real_character_loss() -> None:
    # Whitespace-only differences are preserved...
    assert _content_preserved("a b\n\nc", "a b c") is True
    assert _content_preserved("well-\n\nknown", "well-known") is True
    # ...but a dropped character (the old hyphen-dropping bug) is not.
    assert _content_preserved("state-of-the-art", "state-of-theart") is False


def test_row_sliced_prose_merges_into_one_paragraph() -> None:
    md = _rows(
        "The operator reported that",
        "brief pressure drops near the east",
        "manifold continued while the backup",
        "generator started during the overnight shift.",
    )

    draft = _repair(md)

    assert draft.text == (
        "The operator reported that brief pressure drops near the east "
        "manifold continued while the backup generator started during the "
        "overnight shift.\n"
    )
    assert draft.merge_group_count == 1
    assert draft.original_paragraph_count == 4
    assert draft.repaired_paragraph_count == 1
    assert draft.content_preserved is True


def test_normal_complete_paragraphs_do_not_merge() -> None:
    md = _rows(
        "The operator reported a stable pump.",
        "The crew documented the panel readings.",
        "The inspection closed without findings.",
        "The next visit remains scheduled.",
    )

    draft = _repair(md)

    assert draft.text == md
    assert draft.merge_group_count == 0
    assert draft.repaired_paragraph_count == draft.original_paragraph_count


def test_short_continuation_pair_does_not_collapse_paragraphs() -> None:
    md = _rows(
        "This paragraph ends with and",
        "this begins a separate paragraph.",
    )
    blocks = split_markdown_blocks(md)

    pair_decision = pair_is_continuation(blocks[0], blocks[2])
    draft = repair_blocks(blocks)

    assert pair_decision.merge is True
    assert draft.text == md
    assert draft.merge_group_count == 0


def test_headings_stop_merges() -> None:
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n# Follow-up\n\n"
        + _rows(
            "The maintenance team noted that",
            "temporary vibration near the pump",
            "housing settled after the intake",
            "valve was opened for inspection.",
        )
    )

    draft = _repair(md)

    assert "# Follow-up" in draft.text
    assert "overnight shift.\n\n# Follow-up\n\nThe maintenance team" in draft.text
    assert draft.merge_group_count == 2


def test_lists_stop_merges_and_are_preserved() -> None:
    list_block = "- Inspect valve actuator\n- Photograph panel labels\n"
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n"
        + list_block
        + "\n"
        + _rows(
            "The maintenance team noted that",
            "temporary vibration near the pump",
            "housing settled after the intake",
            "valve was opened for inspection.",
        )
    )

    draft = _repair(md)

    assert list_block in draft.text
    assert "overnight shift.\n\n- Inspect" in draft.text
    assert "panel labels\n\nThe maintenance team" in draft.text


def test_tables_stop_merges_and_are_preserved() -> None:
    table = "| Time | Reading |\n| --- | --- |\n| 10:00 | Low |\n| 10:05 | Stable |\n"
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n"
        + table
        + "\n"
        + _rows(
            "The maintenance team noted that",
            "temporary vibration near the pump",
            "housing settled after the intake",
            "valve was opened for inspection.",
        )
    )

    draft = _repair(md)

    assert table in draft.text
    assert "overnight shift.\n\n| Time | Reading |" in draft.text
    assert "| 10:05 | Stable |\n\nThe maintenance team" in draft.text


def test_code_fences_are_byte_preserved() -> None:
    code_fence = "```python\nvalue = 'and'\n\nprint(value)\n```\n"
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n"
        + code_fence
        + "\n"
        + _rows(
            "The maintenance team noted that",
            "temporary vibration near the pump",
            "housing settled after the intake",
            "valve was opened for inspection.",
        )
    )

    draft = _repair(md)

    assert code_fence in draft.text
    assert draft.text.count("```python") == 1
    assert draft.text.count("print(value)") == 1


def test_image_and_caption_adjacency_is_not_altered() -> None:
    image_and_caption = "![Pump](images/pump.png)\n\nFigure 1: Pump overview\n"
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n"
        + image_and_caption
        + "\n"
        + _rows(
            "The maintenance team noted that",
            "temporary vibration near the pump",
            "housing settled after the intake",
            "valve was opened for inspection.",
        )
    )

    draft = _repair(md)

    assert image_and_caption in draft.text
    assert "overnight shift.\n\n![Pump]" in draft.text
    assert "Figure 1: Pump overview\n\nThe maintenance team" in draft.text


def test_max_paragraph_length_stops_runaway_merge() -> None:
    settings = ParagraphRepairSettings(
        min_continuation_run_blocks=2,
        max_merged_paragraph_chars=65,
    )
    md = _rows(
        "alpha beta gamma delta and",
        "bravo charlie delta echo foxtrot",
        "golf hotel india juliet kilo",
        "lima mike november oscar papa.",
    )

    draft = _repair(md, settings)
    prose_lengths = [
        len(block.text.rstrip("\r\n"))
        for block in split_markdown_blocks(draft.text)
        if block.is_prose
    ]

    assert draft.merge_group_count == 2
    assert max(prose_lengths) <= settings.max_merged_paragraph_chars


def test_ambiguous_hyphenated_continuation_keeps_hyphen() -> None:
    md = _rows(
        "The instrument was cali-",
        "brated before use when",
        "technicians verified the",
        "sensor output during checkout.",
    )

    draft = _repair(md)

    assert "cali-brated before use" in draft.text
    assert "cali- brated" not in draft.text
    # The hyphen join drops no characters, so content is preserved; the
    # ambiguity is surfaced via hyphen_join_count for a downstream gate.
    assert draft.content_preserved is True
    assert draft.hyphen_join_count == 1


def test_hyphenated_compounds_are_not_dehyphenated() -> None:
    md = _rows(
        "The state-of-the-",
        "art method remained well-",
        "known because long-",
        "term records were available.",
    )

    draft = _repair(md)

    assert "state-of-the-art" in draft.text
    assert "well-known" in draft.text
    assert "long-term" in draft.text
    assert "state-of-theart" not in draft.text
    assert "wellknown" not in draft.text
    assert "longterm" not in draft.text
    assert draft.content_preserved is True
    assert draft.hyphen_join_count == 3


def test_hyphen_join_count_is_orthogonal_to_clean_space_merges() -> None:
    # A clean run reports no hyphen joins and stays content-preserved, even
    # when a separate hyphen run shares the document, so one ambiguous hyphen
    # does not taint the whole-document content-preservation guard.
    md = (
        _rows(
            "The operator reported that",
            "brief pressure drops near the east",
            "manifold continued while the backup",
            "generator started during the overnight shift.",
        )
        + "\n# Follow-up\n\n"
        + _rows(
            "The state-of-the-",
            "art method remained well-",
            "known because long-",
            "term records were available.",
        )
    )

    draft = _repair(md)

    assert draft.merge_group_count == 2
    assert draft.hyphen_join_count == 3
    assert draft.content_preserved is True


def test_examples_are_bounded_by_run_settings() -> None:
    settings = ParagraphRepairSettings(
        min_continuation_run_blocks=2,
        max_examples=1,
        max_example_chars=24,
    )
    md = _rows(
        "alpha beta gamma delta and",
        "bravo charlie delta echo foxtrot",
        "golf hotel india juliet kilo",
        "lima mike november oscar papa.",
    )

    draft = _repair(md, settings)

    assert len(draft.examples) == 1
    assert len(draft.examples[0]) <= settings.max_example_chars


def _repair(
    md_text: str,
    settings: ParagraphRepairSettings | None = None,
):
    return repair_blocks(split_markdown_blocks(md_text), settings)


def _rows(*rows: str) -> str:
    return "\n\n".join(rows) + "\n"
