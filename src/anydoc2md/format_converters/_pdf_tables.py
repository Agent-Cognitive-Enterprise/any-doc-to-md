"""PyMuPDF table extraction helpers for the in-house PDF converter."""

from __future__ import annotations

import re
from typing import Any

from anydoc2md.format_converters._pdf_blocks import (
    TableBlock,
    block_column,
)

MARKDOWN_SEPARATOR_RE = re.compile(r"\|\s*:?-{3,}:?\s*(?=\||$)")


def extract_page_tables(
    page: Any,
    *,
    page_num: int,
    page_width: float,
    column_split_ratio: float,
    clean: bool = False,
    fill_empty: bool = True,
) -> tuple[list[TableBlock], list[str]]:
    """Extract PyMuPDF-detected tables from one PDF page.

    Table detection is best-effort. Missing PyMuPDF table support, detector
    failures, and malformed table Markdown are returned as warnings rather than
    raising conversion errors.
    """
    find_tables = getattr(page, "find_tables", None)
    if not callable(find_tables):
        return [], [f"page {page_num}: PyMuPDF page has no find_tables() support"]

    try:
        _suppress_pymupdf_layout_recommendation()
        finder = find_tables()
    except Exception as exc:
        return [], [f"page {page_num}: table detector failed: {exc}"]

    table_blocks: list[TableBlock] = []
    warnings: list[str] = []
    for index, table in enumerate(getattr(finder, "tables", []) or [], start=1):
        table_block, warning = _table_to_block(
            table,
            page_num=page_num,
            table_index=index,
            page_width=page_width,
            column_split_ratio=column_split_ratio,
            clean=clean,
            fill_empty=fill_empty,
        )
        if table_block is not None:
            table_blocks.append(table_block)
        if warning:
            warnings.append(warning)

    return table_blocks, warnings


def looks_like_markdown_table(md: str) -> bool:
    """Return True when Markdown has a plausible GFM table header separator."""
    lines = [line.strip() for line in md.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    if not all("|" in line for line in lines[:2]):
        return False
    return bool(MARKDOWN_SEPARATOR_RE.search(lines[1]))


def _table_to_block(
    table: Any,
    *,
    page_num: int,
    table_index: int,
    page_width: float,
    column_split_ratio: float,
    clean: bool,
    fill_empty: bool,
) -> tuple[TableBlock | None, str]:
    row_count = _int_attr(table, "row_count")
    col_count = _int_attr(table, "col_count")
    if row_count < 2 or col_count < 2:
        return None, (
            f"page {page_num} table {table_index}: ignored table with "
            f"{row_count} row(s) and {col_count} column(s)"
        )

    try:
        markdown = table.to_markdown(clean=clean, fill_empty=fill_empty)
    except TypeError:
        try:
            markdown = table.to_markdown()
        except Exception as exc:
            return None, f"page {page_num} table {table_index}: to_markdown failed: {exc}"
    except Exception as exc:
        return None, f"page {page_num} table {table_index}: to_markdown failed: {exc}"

    if not isinstance(markdown, str) or not looks_like_markdown_table(markdown):
        return None, f"page {page_num} table {table_index}: ignored malformed Markdown table"

    bbox = _bbox_tuple(getattr(table, "bbox", (0.0, 0.0, 0.0, 0.0)))
    return (
        TableBlock(
            page=page_num,
            bbox=bbox,
            markdown=markdown.strip(),
            row_count=row_count,
            col_count=col_count,
            column=block_column(bbox, page_width, column_split_ratio),
        ),
        "",
    )


def _int_attr(obj: Any, name: str) -> int:
    value = getattr(obj, name, 0)
    return value if isinstance(value, int) else 0


def _bbox_tuple(raw_bbox: Any) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = raw_bbox
    except (TypeError, ValueError):
        return (0.0, 0.0, 0.0, 0.0)
    return (float(x0), float(y0), float(x1), float(y1))


def _suppress_pymupdf_layout_recommendation() -> None:
    """Suppress PyMuPDF's optional layout-package recommendation if available."""
    try:
        import fitz
    except ImportError:
        return
    suppress = getattr(fitz, "no_recommend_layout", None)
    if callable(suppress):
        suppress()
