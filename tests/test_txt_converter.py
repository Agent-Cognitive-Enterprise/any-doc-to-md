from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md.format_converters.txt_converter import _para_to_md, convert


# ---------------------------------------------------------------------------
# _para_to_md unit tests
# ---------------------------------------------------------------------------

def test_prose_paragraph_collapses_newlines() -> None:
    para = "Continue routine monitoring\nand keep spare chlorine test strips."
    assert _para_to_md(para) == "Continue routine monitoring and keep spare chlorine test strips."


def test_unordered_list_preserves_newlines() -> None:
    para = "- Item one\n- Item two\n- Item three"
    assert _para_to_md(para) == para


def test_ordered_list_preserves_newlines() -> None:
    para = "1. First step\n2. Second step\n3. Third step"
    assert _para_to_md(para) == para


def test_mixed_list_with_prose_header_preserves_newlines() -> None:
    # A paragraph that starts with a label then has list items.
    para = "Actions:\n- Clear screen\n- Recheck residual"
    assert _para_to_md(para) == para


def test_single_line_prose_unchanged() -> None:
    assert _para_to_md("Just one line.") == "Just one line."


def test_asterisk_list_preserved() -> None:
    para = "* alpha\n* beta"
    assert _para_to_md(para) == para


def test_plus_list_preserved() -> None:
    para = "+ alpha\n+ beta"
    assert _para_to_md(para) == para


def test_field_style_lines_preserved() -> None:
    para = "Location: Hill station supply point\nDate: 2026-04-23"
    assert _para_to_md(para) == para


# ---------------------------------------------------------------------------
# convert integration tests
# ---------------------------------------------------------------------------

def test_convert_preserves_bullet_list(tmp_path: Path) -> None:
    src = tmp_path / "note.txt"
    src.write_text(
        "Observations:\n\n- Intake screen blocked.\n- Residual 0.4 mg/L.\n",
        encoding="utf-8",
    )
    result = convert(src, tmp_path / "out")
    md = (tmp_path / "out" / "index.md").read_text(encoding="utf-8")
    assert "- Intake screen blocked.\n- Residual 0.4 mg/L." in md


def test_convert_preserves_numbered_list(tmp_path: Path) -> None:
    src = tmp_path / "note.txt"
    src.write_text(
        "Actions:\n\n1. Cleared screen.\n2. Rechecked residual.\n",
        encoding="utf-8",
    )
    result = convert(src, tmp_path / "out")
    md = (tmp_path / "out" / "index.md").read_text(encoding="utf-8")
    assert "1. Cleared screen.\n2. Rechecked residual." in md


def test_convert_collapses_wrapped_prose(tmp_path: Path) -> None:
    src = tmp_path / "note.txt"
    src.write_text(
        "Continue routine monitoring\nand keep spare chlorine test strips.\n",
        encoding="utf-8",
    )
    result = convert(src, tmp_path / "out")
    md = (tmp_path / "out" / "index.md").read_text(encoding="utf-8")
    assert "Continue routine monitoring and keep spare chlorine test strips." in md


def test_convert_quickstart_field_note(tmp_path: Path) -> None:
    """Smoke test: field-note.txt must produce recognisable list Markdown."""
    from pathlib import Path as P
    fixture = P(__file__).parent.parent / "examples" / "quickstart" / "field-note.txt"
    if not fixture.exists():
        pytest.skip("quickstart fixture not present")
    result = convert(fixture, tmp_path / "out")
    md = (tmp_path / "out" / "index.md").read_text(encoding="utf-8")
    assert "- Intake screen" in md
    assert "1. Cleared intake screen." in md
    assert "- Chlorine residual" in md
