"""
Format converters: source document → index.md + images/ in a staging directory.

Usage:
    from anydoc2md.format_converters import get_converter

    converter = get_converter(source_path)
    result = converter.convert(source_path, staging_dir, title="...", source_url="...")
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from anydoc2md.format_converters import (
    docx_converter,
    html_converter,
    pdf_converter,
    txt_converter,
)

_CONVERTERS: list[ModuleType] = [
    pdf_converter,
    docx_converter,
    html_converter,
    txt_converter,
]


def get_converter(source_path: Path) -> ModuleType:
    """Return the converter module for source_path, or raise ValueError."""
    for converter in _CONVERTERS:
        if converter.supports(source_path):
            return converter
    raise ValueError(
        f"No converter available for {source_path.suffix!r}. "
        f"Supported: {_supported_extensions()}"
    )


def _supported_extensions() -> str:
    exts: set[str] = set()
    for c in _CONVERTERS:
        exts.update(c.SUPPORTED_EXTENSIONS)
    return ", ".join(sorted(exts))
