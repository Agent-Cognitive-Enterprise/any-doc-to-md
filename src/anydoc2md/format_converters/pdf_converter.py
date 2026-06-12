"""
PDF → Markdown converter.

Extracts text blocks and images from a PDF using PyMuPDF, handles multi-column
layout, emits detected ruled tables as native Markdown tables, attaches figure
captions to their images, filters running page headers, and writes
index.md + images/ to the staging directory.

Overrides (via document.override.yaml or explicit dict):
    column_split_ratio      float   0.55   x > page_width * ratio → right column
    min_text_len            int    10      discard blocks shorter than this
    running_header_min_pages int   3       heading on ≥N pages → running header
    table_extraction        str    pymupdf pymupdf|off
    table_markdown_clean    bool   false   pass clean=... to Table.to_markdown()
    table_markdown_fill_empty bool true    pass fill_empty=... to Table.to_markdown()
    table_text_suppression_overlap float 0.65
        suppress flattened text at/above this bbox overlap
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anydoc2md.format_converters._pdf_assemble import TABLE_TEXT_SUPPRESSION_OVERLAP
from anydoc2md.format_converters._pdf_assemble import assemble_markdown as _assemble
from anydoc2md.format_converters._pdf_blocks import ImageBlock as _ImageBlock  # noqa: F401
from anydoc2md.format_converters._pdf_blocks import TextBlock as _TextBlock  # noqa: F401
from anydoc2md.format_converters._pdf_extract import extract_pdf_blocks as _extract  # noqa: F401
from anydoc2md.format_converters._pdf_extract import extract_pdf_blocks_v2 as _extract_v2
from anydoc2md.format_converters.base import (
    INDEX_FILENAME,
    ConversionResult,
    load_overrides,
    resolve_source_reference,
)

SUPPORTED_EXTENSIONS = {".pdf"}


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def convert(
    source_path: Path,
    staging_dir: Path,
    *,
    title: str = "",
    source_url: str = "",
    overrides: dict[str, Any] | None = None,
) -> ConversionResult:
    """
    Convert a PDF to index.md + images/ in staging_dir.
    Reads document.override.yaml from staging_dir automatically.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_overrides(staging_dir, overrides)

    column_split_ratio: float = float(cfg.get("column_split_ratio", 0.55))
    min_text_len: int = int(cfg.get("min_text_len", 10))
    running_header_min_pages: int = int(cfg.get("running_header_min_pages", 3))
    table_extraction = cfg.get("table_extraction", "pymupdf")
    table_markdown_clean: bool = _bool_override(cfg.get("table_markdown_clean"), False)
    table_markdown_fill_empty: bool = _bool_override(
        cfg.get("table_markdown_fill_empty"),
        True,
    )
    table_text_suppression_overlap: float = float(
        cfg.get("table_text_suppression_overlap", TABLE_TEXT_SUPPRESSION_OVERLAP)
    )

    resolved_title = title or source_path.stem.replace("_", " ")
    resolved_url = resolve_source_reference(source_path, source_url)

    images_dir = staging_dir / "images"
    extraction = _extract_v2(
        source_path,
        images_dir,
        column_split_ratio=column_split_ratio,
        min_text_len=min_text_len,
        table_extraction=table_extraction,
        table_markdown_clean=table_markdown_clean,
        table_markdown_fill_empty=table_markdown_fill_empty,
    )

    md = _assemble(
        resolved_title,
        resolved_url,
        extraction.text_blocks,
        extraction.image_blocks,
        running_header_min_pages,
        table_blocks=extraction.table_blocks,
        table_text_suppression_overlap=table_text_suppression_overlap,
    )

    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=len(extraction.image_blocks),
        warnings=extraction.warnings,
    )


def _bool_override(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)
