from __future__ import annotations

from anydoc2md.format_converters import pdf_converter
from anydoc2md.format_converters._pdf_assemble import assemble_markdown
from anydoc2md.format_converters._pdf_blocks import ImageBlock, TextBlock
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
