"""
Plain text → Markdown converter.

Wraps plain text in a minimal Markdown document.  Paragraph detection uses
blank-line separation.  No images.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from anydoc2md.format_converters.base import (
    INDEX_FILENAME,
    ConversionResult,
    load_overrides,
    resolve_source_reference,
)

SUPPORTED_EXTENSIONS = {".txt", ".text"}

_LIST_LINE = re.compile(r"^\s*(?:[-*+•]|\d+\.)\s")
_FIELD_LINE = re.compile(r"^\w[\w\s]*:\s+\S")


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def _para_to_md(para: str) -> str:
    """Preserve list and field-style structure; collapse line-wrapped prose."""
    lines = para.splitlines()
    if any(_LIST_LINE.match(line) or _FIELD_LINE.match(line) for line in lines):
        return para
    return " ".join(lines)


def convert(
    source_path: Path,
    staging_dir: Path,
    *,
    title: str = "",
    source_url: str = "",
    overrides: dict[str, Any] | None = None,
) -> ConversionResult:
    staging_dir.mkdir(parents=True, exist_ok=True)
    load_overrides(staging_dir, overrides)  # honour override file even if unused yet

    resolved_title = title or source_path.stem.replace("_", " ")
    resolved_url = resolve_source_reference(source_path, source_url)

    raw = source_path.read_text(encoding="utf-8", errors="replace")

    # Split on blank lines to form paragraphs
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

    lines: list[str] = [f"# {resolved_title}\n", f"**Source:** {resolved_url}\n", ""]
    for para in paragraphs:
        lines.append(_para_to_md(para) + "\n")

    md = "\n".join(lines)
    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=0,
    )
