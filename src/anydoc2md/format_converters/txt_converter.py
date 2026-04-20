"""
Plain text → Markdown converter.

Wraps plain text in a minimal Markdown document.  Paragraph detection uses
blank-line separation.  No images.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anydoc2md.format_converters.base import (
    INDEX_FILENAME,
    ConversionResult,
    load_overrides,
)

SUPPORTED_EXTENSIONS = {".txt", ".text"}


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
    staging_dir.mkdir(parents=True, exist_ok=True)
    load_overrides(staging_dir, overrides)  # honour override file even if unused yet

    resolved_title = title or source_path.stem.replace("_", " ")
    resolved_url = source_url or f"file://{source_path.resolve()}"

    raw = source_path.read_text(encoding="utf-8", errors="replace")

    # Split on blank lines to form paragraphs
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

    lines: list[str] = [f"# {resolved_title}\n", f"**Source:** {resolved_url}\n", ""]
    for para in paragraphs:
        # Collapse internal newlines (line-wrapped text)
        collapsed = " ".join(para.splitlines())
        lines.append(collapsed + "\n")

    md = "\n".join(lines)
    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=0,
    )
