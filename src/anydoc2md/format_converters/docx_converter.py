"""
DOCX → Markdown converter.

Converts a .docx file to PDF via LibreOffice headless, then delegates to
pdf_converter for layout-aware extraction.  Requires:
    libreoffice-core  libreoffice-writer  (apt)

Overrides: all pdf_converter overrides apply (column_split_ratio, etc.)
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from anydoc2md.format_converters.base import ConversionResult, load_overrides
from anydoc2md.format_converters import pdf_converter

SUPPORTED_EXTENSIONS = {".docx", ".doc", ".odt", ".rtf"}
_LIBREOFFICE = "libreoffice"


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
    Convert a DOCX (or ODF/RTF) to index.md + images/ via LibreOffice → PDF → pdf_converter.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_overrides(staging_dir, overrides)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _libreoffice_to_pdf(source_path, tmp_path)

        pdf_path = tmp_path / (source_path.stem + ".pdf")
        if not pdf_path.exists():
            raise RuntimeError(
                f"LibreOffice did not produce a PDF for {source_path.name}. "
                f"Files in tmp: {list(tmp_path.iterdir())}"
            )

        return pdf_converter.convert(
            pdf_path,
            staging_dir,
            title=title or source_path.stem.replace("_", " "),
            source_url=source_url or f"file://{source_path.resolve()}",
            overrides=cfg,
        )


def _libreoffice_to_pdf(source_path: Path, output_dir: Path) -> None:
    result = subprocess.run(
        [
            _LIBREOFFICE,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(source_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice conversion failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
