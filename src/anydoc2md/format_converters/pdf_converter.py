"""
PDF → Markdown converter.

Extracts text blocks and images from a PDF using PyMuPDF, handles multi-column
layout, attaches figure captions to their images, filters running page headers,
and writes index.md + images/ to the staging directory.

Overrides (via document.override.yaml or explicit dict):
    column_split_ratio      float   0.55   x > page_width * ratio → right column
    min_text_len            int    1       preserve nonempty text by default
    running_header_min_pages int   3       repeated edge furniture on ≥N pages
"""
from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from anydoc2md.format_converters._pdf_assemble import assemble_markdown as _assemble
from anydoc2md.format_converters._pdf_blocks import ImageBlock as _ImageBlock  # noqa: F401
from anydoc2md.format_converters._pdf_blocks import TextBlock as _TextBlock  # noqa: F401
from anydoc2md.format_converters._pdf_extract import extract_pdf_blocks as _extract
from anydoc2md.format_converters._pdf_page_furniture import removed_block_audit
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
    min_text_len: int = int(cfg.get("min_text_len", 1))
    running_header_min_pages: int = int(cfg.get("running_header_min_pages", 3))

    resolved_title = title or source_path.stem.replace("_", " ")
    resolved_url = resolve_source_reference(source_path, source_url)

    images_dir = staging_dir / "images"
    text_blocks, image_blocks, extraction_drops = _extract(
        source_path,
        images_dir,
        column_split_ratio=column_split_ratio,
        min_text_len=min_text_len,
    )

    audit_path = staging_dir / "removed-blocks.json"
    audit_path.write_text(
        json.dumps(extraction_drops + removed_block_audit(text_blocks, running_header_min_pages),
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    md = _assemble(
        resolved_title,
        resolved_url,
        text_blocks,
        image_blocks,
        running_header_min_pages,
    )

    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=len(image_blocks),
    )
