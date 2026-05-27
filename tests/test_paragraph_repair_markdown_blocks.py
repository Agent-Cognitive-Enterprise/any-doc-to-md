from __future__ import annotations

from anydoc2md.paragraph_repair.markdown_blocks import (
    classify_line,
    is_caption_line,
    is_heading,
    is_image_line,
    is_list_item,
    is_table_like,
    split_markdown_blocks,
    reconstruct_markdown,
)


def _kinds(md_text: str) -> list[str]:
    return [block.kind for block in split_markdown_blocks(md_text)]


def test_row_sliced_prose_splits_into_prose_and_blank_blocks() -> None:
    md = "The pump started\n\nwithout a stable\n\npressure reading.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert [block.kind for block in blocks] == [
        "prose",
        "blank",
        "prose",
        "blank",
        "prose",
    ]
    assert [block.text.strip() for block in blocks if block.is_prose] == [
        "The pump started",
        "without a stable",
        "pressure reading.",
    ]


def test_normal_wrapped_paragraph_stays_one_prose_block() -> None:
    md = "The pump started\nwithout a stable\npressure reading.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert len(blocks) == 1
    assert blocks[0].kind == "prose"


def test_headings_are_hard_boundaries() -> None:
    md = "# Report\n\nThe pump started.\n"

    blocks = split_markdown_blocks(md)

    assert _kinds(md) == ["heading", "blank", "prose"]
    assert blocks[0].is_hard_boundary
    assert is_heading("# Report")


def test_bullet_and_numbered_lists_are_structural() -> None:
    md = "- Inspect valve\n- Photograph panel\n\n1. Open gate\n2. Log reading\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["list_item", "blank", "list_item"]
    assert all(
        not block.is_prose
        for block in blocks
        if block.kind == "list_item"
    )
    assert is_list_item("- [ ] Inspect valve")
    assert is_list_item("2. Log reading")


def test_pipe_table_is_structural() -> None:
    md = "| Time | Reading |\n| --- | --- |\n| 10:00 | Low |\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["table"]
    assert blocks[0].is_hard_boundary
    assert is_table_like("| --- | --- |")


def test_whitespace_table_rows_are_structural() -> None:
    md = "Time      Reading\n10:00     Low\n10:05     Stable\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["table"]
    assert classify_line("10:00     Low") == "table"


def test_fenced_code_block_is_single_preserved_structural_block() -> None:
    md = "```text\nThis looks like prose\n\nbut must not merge\n```\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert len(blocks) == 1
    assert blocks[0].kind == "code_fence"
    assert blocks[0].text == md
    assert blocks[0].is_hard_boundary


def test_fenced_code_after_prose_without_blank_is_not_absorbed() -> None:
    md = "paragraph one\n```py\nfoo\n```\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert [block.kind for block in blocks] == ["prose", "code_fence"]
    assert blocks[1].text == "```py\nfoo\n```\n"
    assert classify_line("```py") == "code_fence"


def test_images_and_captions_are_structural() -> None:
    md = "![Pump panel](images/panel.png)\n\nFigure 1. Pump control panel.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["image", "blank", "caption"]
    assert is_image_line("![Pump panel](images/panel.png)")
    assert is_caption_line("Table 1. Pressure readings.")


def test_caption_detection_does_not_match_prose_sentences() -> None:
    assert classify_line("Table 1 below shows readings.") == "prose"
    assert classify_line("Figure 1 said the report was late.") == "prose"
    assert is_caption_line("Figure 1. Pump control panel.")
    assert is_caption_line("Table 1: Pressure readings.")


def test_inline_pipes_in_prose_are_not_tables() -> None:
    assert classify_line("use a|b|c notation") == "prose"
    assert is_table_like("| a | b |")


def test_pipe_table_without_edge_pipes_is_one_table_block() -> None:
    md = "Time | Reading\n--- | ---\n10:00 | Low\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert [block.kind for block in blocks] == ["table"]


def test_pipe_table_without_edge_pipes_after_prose_breaks_paragraph() -> None:
    md = "Some intro line.\nTime | Reading\n--- | ---\n10:00 | Low\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert [block.kind for block in blocks] == ["prose", "table"]


def test_double_spaces_in_prose_are_not_whitespace_tables() -> None:
    assert classify_line("Two  words") == "prose"
    assert classify_line("She  arrived  late") == "prose"


def test_blockquotes_are_structural() -> None:
    md = "> This looks like prose\n> but is quoted evidence.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["blockquote"]
    assert blocks[0].is_hard_boundary


def test_front_matter_at_document_start_is_structural() -> None:
    md = "---\ntitle: Pump note\n---\n\n# Report\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["front_matter", "blank", "heading"]
    assert blocks[0].text == "---\ntitle: Pump note\n---\n"


def test_front_matter_requires_yaml_like_content() -> None:
    md = "---\n# Title\n---\n\nbody\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == [
        "horizontal_rule",
        "heading",
        "horizontal_rule",
        "blank",
        "prose",
    ]


def test_setext_headings_are_structural_blocks() -> None:
    md = "Big Title\n=========\n\nbody\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["heading", "blank", "prose"]
    assert blocks[0].text == "Big Title\n=========\n"


def test_setext_dash_heading_is_not_horizontal_rule() -> None:
    md = "Big Title\n---------\n\nbody\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["heading", "blank", "prose"]


def test_horizontal_rule_is_not_front_matter_without_closing_marker() -> None:
    md = "---\n\nThe pump started.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["horizontal_rule", "blank", "prose"]


def test_raw_html_block_is_structural() -> None:
    md = "<div>\nThis text is inside raw HTML.\n</div>\n\nPlain paragraph.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["html", "blank", "prose"]
    assert all(
        not block.is_prose
        for block in blocks
        if block.kind == "html"
    )


def test_raw_html_closing_tag_stops_block_without_blank() -> None:
    md = "<div>\nHTML text\n</div>\nPlain paragraph.\n"

    blocks = split_markdown_blocks(md)

    assert reconstruct_markdown(blocks) == md
    assert _kinds(md) == ["html", "prose"]


def test_blank_blocks_are_not_hard_boundaries() -> None:
    blocks = split_markdown_blocks("a\n\nb\n")
    blank = blocks[1]

    assert blank.is_blank
    assert not blank.is_prose
    assert not blank.is_hard_boundary
