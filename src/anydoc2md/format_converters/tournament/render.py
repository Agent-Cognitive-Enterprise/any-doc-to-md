"""
Render candidate Markdown into a simple paginated PDF for audit purposes.

This is intentionally minimal: it creates a readable audit artifact with stable
pagination and text extraction, not a visually faithful webpage render.
"""
from __future__ import annotations

from pathlib import Path
import textwrap

import fitz

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 48
FONT_SIZE = 11
LINE_HEIGHT = 15
MAX_CHARS_PER_LINE = 88


def render_markdown_to_audit_pdf(markdown_path: Path, output_path: Path) -> Path:
    """Render Markdown text to a simple multi-page PDF and return output_path."""
    text = markdown_path.read_text(encoding="utf-8")
    lines = _markdown_to_lines(text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN

    for line in lines:
        if y > PAGE_HEIGHT - MARGIN:
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = MARGIN
        page.insert_text(
            fitz.Point(MARGIN, y),
            line,
            fontsize=FONT_SIZE,
            fontname="courier",
        )
        y += LINE_HEIGHT

    doc.save(output_path)
    doc.close()
    return output_path


def _markdown_to_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    wrapped_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.expandtabs(4).rstrip()
        if not line:
            wrapped_lines.append("")
            continue
        prefixes = ("# ", "## ", "### ", "- ", "* ", "1. ", "2. ", "3. ")
        if line.startswith(prefixes):
            wrapped_lines.append(line[:MAX_CHARS_PER_LINE])
            line = line[MAX_CHARS_PER_LINE:]
            if not line:
                continue
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=MAX_CHARS_PER_LINE,
                replace_whitespace=False,
                drop_whitespace=False,
            ) or [""]
        )
    return wrapped_lines or [""]
