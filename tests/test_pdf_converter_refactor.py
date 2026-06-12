from __future__ import annotations

from anydoc2md.format_converters import pdf_converter
from anydoc2md.format_converters._pdf_assemble import assemble_markdown
from anydoc2md.format_converters._pdf_blocks import (
    ImageBlock,
    TableBlock,
    TextBlock,
    sort_key,
)
from anydoc2md.format_converters._pdf_extract import extract_pdf_blocks


def test_pdf_converter_facade_preserves_private_aliases() -> None:
    assert pdf_converter._extract is extract_pdf_blocks
    assert pdf_converter._assemble is assemble_markdown
    assert pdf_converter._TextBlock is TextBlock
    assert pdf_converter._ImageBlock is ImageBlock


def test_assemble_markdown_attaches_caption_to_nearest_preceding_image() -> None:
    text = TextBlock(
        page=1,
        bbox=(72.0, 72.0, 300.0, 90.0),
        text="Opening paragraph.",
        block_kind="paragraph",
        avg_font_size=12.0,
        column=0,
    )
    image = ImageBlock(
        page=1,
        bbox=(72.0, 110.0, 300.0, 250.0),
        filename="images/fig.png",
        width=128,
        height=128,
        page_width=600.0,
        column=0,
    )
    caption = TextBlock(
        page=1,
        bbox=(72.0, 260.0, 300.0, 280.0),
        text="Figure 1. Pump curve.",
        block_kind="paragraph",
        avg_font_size=12.0,
        column=0,
    )

    markdown = assemble_markdown(
        "Report",
        "report.pdf",
        [text, caption],
        [image],
        running_header_min_pages=3,
    )

    assert markdown.index('<img src="images/fig.png"') < markdown.index("*Figure 1. Pump curve.*")


def test_table_block_uses_existing_pdf_block_sort_order() -> None:
    text = TextBlock(
        page=1,
        bbox=(72.0, 80.0, 300.0, 96.0),
        text="Opening paragraph.",
        block_kind="paragraph",
        avg_font_size=12.0,
        column=0,
    )
    table = TableBlock(
        page=1,
        bbox=(72.0, 120.0, 360.0, 210.0),
        markdown="|A|B|\n|---|---|\n|1|2|",
        row_count=2,
        col_count=2,
        column=0,
    )
    image = ImageBlock(
        page=1,
        bbox=(72.0, 240.0, 300.0, 330.0),
        filename="images/fig.png",
        width=128,
        height=128,
        page_width=600.0,
        column=0,
    )
    right_column_text = TextBlock(
        page=1,
        bbox=(380.0, 40.0, 540.0, 60.0),
        text="Right column starts after the left column.",
        block_kind="paragraph",
        avg_font_size=12.0,
        column=1,
    )

    ordered = sorted(
        [image, right_column_text, table, text],
        key=sort_key,
    )

    assert ordered == [text, table, image, right_column_text]


def test_assemble_markdown_empty_table_blocks_is_no_op() -> None:
    text = TextBlock(
        page=1,
        bbox=(72.0, 80.0, 300.0, 96.0),
        text="Opening paragraph.",
        block_kind="paragraph",
        avg_font_size=12.0,
        column=0,
    )

    without_tables = assemble_markdown(
        "Report",
        "report.pdf",
        [text],
        [],
        running_header_min_pages=3,
    )
    with_empty_tables = assemble_markdown(
        "Report",
        "report.pdf",
        [text],
        [],
        running_header_min_pages=3,
        table_blocks=[],
    )

    assert with_empty_tables == without_tables


def test_assemble_markdown_emits_table_block_as_native_markdown() -> None:
    table = TableBlock(
        page=1,
        bbox=(72.0, 120.0, 360.0, 210.0),
        markdown="|Quarter|Revenue|\n|---|---|\n|Q1|9|",
        row_count=2,
        col_count=2,
        column=0,
    )

    markdown = assemble_markdown(
        "Report",
        "report.pdf",
        [],
        [],
        running_header_min_pages=3,
        table_blocks=[table],
    )

    assert "|Quarter|Revenue|" in markdown
    assert "|---|---|" in markdown
    assert "|Q1|9|" in markdown
    assert "```" not in markdown


def test_assemble_markdown_keeps_table_caption_with_table() -> None:
    caption = TextBlock(
        page=1,
        bbox=(72.0, 90.0, 360.0, 108.0),
        text="Table 1. Quarterly results.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    table = TableBlock(
        page=1,
        bbox=(72.0, 120.0, 360.0, 210.0),
        markdown="|Quarter|Revenue|\n|---|---|\n|Q1|9|",
        row_count=2,
        col_count=2,
        column=0,
    )
    discussion = TextBlock(
        page=2,
        bbox=(72.0, 80.0, 360.0, 96.0),
        text="Discussion follows on the next page.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    conclusion = TextBlock(
        page=3,
        bbox=(72.0, 80.0, 360.0, 96.0),
        text="Conclusion follows on the final page.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )

    markdown = assemble_markdown(
        "Report",
        "report.pdf",
        [caption, discussion, conclusion],
        [],
        running_header_min_pages=3,
        table_blocks=[table],
    )

    assert markdown.index("*Table 1. Quarterly results.*") < markdown.index("|Quarter|Revenue|")
    assert markdown.index("|Quarter|Revenue|") < markdown.index("Discussion follows")
    assert markdown.index("Discussion follows") < markdown.index("Conclusion follows")


def test_assemble_markdown_suppresses_text_inside_table_bbox() -> None:
    caption = TextBlock(
        page=1,
        bbox=(72.0, 90.0, 360.0, 108.0),
        text="Table 1. Equipment status by owner.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    flattened_cell = TextBlock(
        page=1,
        bbox=(84.0, 142.0, 130.0, 158.0),
        text="Pump A",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    after_table = TextBlock(
        page=1,
        bbox=(72.0, 240.0, 420.0, 258.0),
        text="After the table, this paragraph must survive.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    table = TableBlock(
        page=1,
        bbox=(72.0, 130.0, 382.0, 214.0),
        markdown="|Component|Status|\n|---|---|\n|Pump A|Stable|",
        row_count=2,
        col_count=2,
        column=0,
    )

    markdown = assemble_markdown(
        "Report",
        "report.pdf",
        [caption, flattened_cell, after_table],
        [],
        running_header_min_pages=3,
        table_blocks=[table],
    )

    assert "*Table 1. Equipment status by owner.*" in markdown
    assert "|Pump A|Stable|" in markdown
    assert markdown.count("Pump A") == 1
    assert "After the table, this paragraph must survive." in markdown


def test_assemble_markdown_keeps_caption_in_reading_order_when_not_adjacent() -> None:
    caption = TextBlock(
        page=1,
        bbox=(72.0, 90.0, 360.0, 106.0),
        text="Table 1. Header caption.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    intervening = TextBlock(
        page=1,
        bbox=(72.0, 112.0, 360.0, 128.0),
        text="Intervening sentence that is not part of the table.",
        block_kind="paragraph",
        avg_font_size=10.0,
        column=0,
    )
    table = TableBlock(
        page=1,
        bbox=(72.0, 140.0, 360.0, 210.0),
        markdown="|X|Y|\n|---|---|\n|1|2|",
        row_count=2,
        col_count=2,
        column=0,
    )

    markdown = assemble_markdown(
        "Report",
        "report.pdf",
        [caption, intervening],
        [],
        running_header_min_pages=3,
        table_blocks=[table],
    )

    # The caption must not leapfrog the intervening body text to hug the table;
    # natural reading order is preserved.
    assert markdown.index("*Table 1. Header caption.*") < markdown.index("Intervening sentence")
    assert markdown.index("Intervening sentence") < markdown.index("|X|Y|")
