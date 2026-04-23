from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from anydoc2md.format_converters.adapters import unstructured
from anydoc2md.format_converters.adapters._unstructured_markdown import (
    render_elements_to_markdown,
)


@dataclass
class _Metadata:
    category_depth: int | None = None
    text_as_html: str | None = None


@dataclass
class _Element:
    category: str
    text: str = ""
    metadata: _Metadata | None = None


def _txt_source(tmp_path: Path, content: str = "Para one.\n\nPara two.") -> Path:
    path = tmp_path / "doc.txt"
    path.write_text(content, encoding="utf-8")
    return path


def test_missing_unstructured_package_returns_error(tmp_path: Path) -> None:
    src = _txt_source(tmp_path)
    with patch(
        "anydoc2md.format_converters.adapters.unstructured._get_version",
        return_value="not_installed",
    ):
        result = unstructured.run(src, tmp_path / "staging")

    assert result.status == "error"
    assert "pip install 'unstructured[all-docs]'" in result.error_message


def test_unstructured_supports_pdf() -> None:
    assert unstructured.supports(Path("doc.pdf")) is True


def test_unstructured_rejects_png() -> None:
    assert unstructured.supports(Path("doc.png")) is False


def test_render_elements_to_markdown_handles_core_categories() -> None:
    markdown = render_elements_to_markdown(
        [
            _Element("Title", "Main title", _Metadata(category_depth=0)),
            _Element("NarrativeText", "Paragraph."),
            _Element("ListItem", "1. First item"),
            _Element("ListItem", "- Second item"),
            _Element("Table", "fallback", _Metadata(text_as_html="<table><tr><td>X</td></tr></table>")),
            _Element("FigureCaption", "Figure 1"),
            _Element("PageBreak"),
            _Element("Header", "ignored"),
        ]
    )

    assert "# Main title" in markdown
    assert "Paragraph." in markdown
    assert "- First item" in markdown
    assert "- Second item" in markdown
    assert "<table><tr><td>X</td></tr></table>" in markdown
    assert "*Figure 1*" in markdown
    assert "---" in markdown
    assert "ignored" not in markdown


def test_render_elements_to_markdown_uses_table_text_when_html_missing() -> None:
    markdown = render_elements_to_markdown([_Element("Table", "Cell A | Cell B")])

    assert markdown == "Cell A | Cell B"
