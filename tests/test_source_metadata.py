from __future__ import annotations

from pathlib import Path

import fitz

from anydoc2md.format_converters import docx_converter, html_converter, pdf_converter, txt_converter
from anydoc2md.format_converters.base import ConversionResult, INDEX_FILENAME


def _read_index(staging_dir: Path) -> str:
    return (staging_dir / INDEX_FILENAME).read_text(encoding="utf-8")


def test_txt_converter_default_source_metadata_does_not_leak_absolute_path(tmp_path: Path) -> None:
    source = tmp_path / "private" / "field-note.txt"
    source.parent.mkdir()
    source.write_text("Line one.\n\nLine two.", encoding="utf-8")

    result = txt_converter.convert(source, tmp_path / "staging")

    md = _read_index(result.staging_dir)
    assert "**Source:** field-note.txt" in md
    assert "file://" not in md
    assert str(source.parent) not in md
    assert result.source_url == "field-note.txt"


def test_explicit_source_url_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "field-note.txt"
    source.write_text("Line one.", encoding="utf-8")

    result = txt_converter.convert(
        source,
        tmp_path / "staging",
        source_url="https://example.test/docs/field-note.txt",
    )

    md = _read_index(result.staging_dir)
    assert "**Source:** https://example.test/docs/field-note.txt" in md
    assert result.source_url == "https://example.test/docs/field-note.txt"


def test_html_converter_default_source_metadata_does_not_leak_absolute_path(tmp_path: Path) -> None:
    source = tmp_path / "private" / "brief.html"
    source.parent.mkdir()
    source.write_text("<html><title>Brief</title><body><p>Hello.</p></body></html>", encoding="utf-8")

    result = html_converter.convert(source, tmp_path / "staging")

    md = _read_index(result.staging_dir)
    assert "**Source:** brief.html" in md
    assert "file://" not in md
    assert str(source.parent) not in md


def test_pdf_converter_default_source_metadata_does_not_leak_absolute_path(tmp_path: Path) -> None:
    source = tmp_path / "private" / "report.pdf"
    source.parent.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Alpha report paragraph with enough text.")
    doc.save(source)
    doc.close()

    result = pdf_converter.convert(source, tmp_path / "staging")

    md = _read_index(result.staging_dir)
    assert "**Source:** report.pdf" in md
    assert "file://" not in md
    assert str(source.parent) not in md


def test_docx_converter_passes_sanitized_default_source_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "private" / "proposal.docx"
    source.parent.mkdir()
    source.write_bytes(b"fake docx")
    captured: dict[str, str] = {}

    def fake_libreoffice_to_pdf(_source_path: Path, output_dir: Path) -> None:
        (output_dir / "proposal.pdf").write_bytes(b"%PDF-1.4")

    def fake_pdf_convert(
        _pdf_path: Path,
        staging_dir: Path,
        *,
        title: str,
        source_url: str,
        overrides: dict,
    ) -> ConversionResult:
        captured["title"] = title
        captured["source_url"] = source_url
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / INDEX_FILENAME).write_text("# Proposal\n", encoding="utf-8")
        return ConversionResult(staging_dir, title, source_url, image_count=0)

    monkeypatch.setattr(docx_converter, "_libreoffice_to_pdf", fake_libreoffice_to_pdf)
    monkeypatch.setattr(docx_converter.pdf_converter, "convert", fake_pdf_convert)

    docx_converter.convert(source, tmp_path / "staging")

    assert captured["source_url"] == "proposal.docx"
