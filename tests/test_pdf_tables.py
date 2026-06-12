from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md.format_converters._pdf_blocks import TableBlock
from anydoc2md.format_converters._pdf_tables import (
    extract_page_tables,
    looks_like_markdown_table,
)


def test_looks_like_markdown_table_accepts_gfm_table() -> None:
    assert looks_like_markdown_table("|A|B|\n|---|---|\n|1|2|")


@pytest.mark.parametrize(
    "markdown",
    [
        "",
        "not a table",
        "|A|B|",
        "|A|B|\n|bad|bad|",
        "A | B\n--- ---",
    ],
)
def test_looks_like_markdown_table_rejects_non_tables(markdown: str) -> None:
    assert not looks_like_markdown_table(markdown)


def test_extract_page_tables_warns_when_find_tables_missing() -> None:
    tables, warnings = extract_page_tables(
        object(),
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings
    assert "find_tables" in warnings[0]


def test_extract_page_tables_returns_warning_when_detector_raises() -> None:
    class RaisingPage:
        def find_tables(self):
            raise RuntimeError("table detector failed")

    tables, warnings = extract_page_tables(
        RaisingPage(),
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings
    assert "table detector failed" in warnings[0]


def test_extract_page_tables_filters_malformed_markdown() -> None:
    page = _FakePage([
        _FakeTable(
            markdown="not a table",
            row_count=3,
            col_count=3,
        )
    ])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings == ["page 1 table 1: ignored malformed Markdown table"]


def test_extract_page_tables_supports_no_arg_to_markdown_fallback() -> None:
    page = _FakePage([
        _LegacyTable(
            markdown="|A|B|\n|---|---|\n|1|2|",
            row_count=2,
            col_count=2,
        )
    ])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert warnings == []
    assert len(tables) == 1
    assert tables[0].markdown == "|A|B|\n|---|---|\n|1|2|"


def test_extract_page_tables_ignores_undersized_table() -> None:
    page = _FakePage([
        _FakeTable(
            markdown="|A|B|\n|---|---|\n|1|2|",
            row_count=1,
            col_count=3,
        )
    ])

    tables, warnings = extract_page_tables(
        page,
        page_num=2,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings == [
        "page 2 table 1: ignored table with 1 row(s) and 3 column(s)"
    ]


def test_extract_page_tables_ignores_table_with_non_int_dimensions() -> None:
    page = _FakePage([_NonIntCountTable()])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings == [
        "page 1 table 1: ignored table with 0 row(s) and 3 column(s)"
    ]


def test_extract_page_tables_warns_when_to_markdown_raises() -> None:
    page = _FakePage([_MarkdownErrorTable()])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings == ["page 1 table 1: to_markdown failed: kaboom"]


def test_extract_page_tables_warns_when_to_markdown_fallback_raises() -> None:
    page = _FakePage([_DoubleFailTable()])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert tables == []
    assert warnings == ["page 1 table 1: to_markdown failed: boom"]


def test_extract_page_tables_uses_zero_bbox_when_bbox_malformed() -> None:
    page = _FakePage([
        _BadBboxTable(
            markdown="|A|B|\n|---|---|\n|1|2|",
            row_count=2,
            col_count=2,
        )
    ])

    tables, warnings = extract_page_tables(
        page,
        page_num=1,
        page_width=612.0,
        column_split_ratio=0.55,
    )

    assert warnings == []
    assert len(tables) == 1
    assert tables[0].bbox == (0.0, 0.0, 0.0, 0.0)
    assert tables[0].column == 0


def test_extract_page_tables_reads_generated_ruled_grid_pdf(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fitz = pytest.importorskip("fitz")
    pdf_path = tmp_path / "ruled-table.pdf"
    _write_ruled_table_pdf(pdf_path, fitz)

    with fitz.open(pdf_path) as doc:
        page = doc[0]
        tables, warnings = extract_page_tables(
            page,
            page_num=1,
            page_width=page.rect.width,
            column_split_ratio=0.55,
        )

    captured = capsys.readouterr()
    assert "pymupdf_layout" not in captured.out + captured.err
    assert warnings == []
    assert len(tables) == 1

    table = tables[0]
    assert isinstance(table, TableBlock)
    assert table.page == 1
    assert table.row_count == 3
    assert table.col_count == 3
    assert table.source == "pymupdf"
    assert table.column == 0
    assert table.bbox == pytest.approx((72.0, 130.0, 382.0, 214.0), abs=1.0)
    assert "|Component|Status|Owner|" in table.markdown
    assert "|---|---|---|" in table.markdown
    assert "|Pump A|Stable|Rina|" in table.markdown
    assert "|Valve B|Watch|Omar|" in table.markdown


def _write_ruled_table_pdf(path: Path, fitz_module) -> None:
    doc = fitz_module.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Quarterly Metrics", fontsize=14)
    page.insert_text((72, 104), "Table 1. Equipment status by owner.", fontsize=10)

    x0, y0 = 72, 130
    col_widths = [100, 110, 100]
    row_height = 28
    rows = [
        ["Component", "Status", "Owner"],
        ["Pump A", "Stable", "Rina"],
        ["Valve B", "Watch", "Omar"],
    ]
    xs = [x0]
    for width in col_widths:
        xs.append(xs[-1] + width)
    ys = [y0 + i * row_height for i in range(len(rows) + 1)]

    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=0.7)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=0.7)
    for row_index, row in enumerate(rows):
        for col_index, text in enumerate(row):
            page.insert_text(
                (xs[col_index] + 6, ys[row_index] + 18),
                text,
                fontsize=10,
            )

    page.insert_text(
        (72, ys[-1] + 28),
        "After the table, this paragraph must survive.",
        fontsize=10,
    )
    doc.save(path)
    doc.close()


class _FakeFinder:
    def __init__(self, tables: list[object]) -> None:
        self.tables = tables


class _FakePage:
    def __init__(self, tables: list[object]) -> None:
        self._tables = tables

    def find_tables(self) -> _FakeFinder:
        return _FakeFinder(self._tables)


class _FakeTable:
    bbox = (72.0, 130.0, 382.0, 214.0)

    def __init__(self, *, markdown: str, row_count: int, col_count: int) -> None:
        self._markdown = markdown
        self.row_count = row_count
        self.col_count = col_count

    def to_markdown(self, *, clean: bool = False, fill_empty: bool = True) -> str:
        return self._markdown


class _LegacyTable(_FakeTable):
    def to_markdown(self) -> str:  # type: ignore[override]
        return self._markdown


class _NonIntCountTable:
    bbox = (72.0, 130.0, 382.0, 214.0)
    row_count = "many"
    col_count = 3

    def to_markdown(self, *, clean: bool = False, fill_empty: bool = True) -> str:
        return "|A|B|\n|---|---|\n|1|2|"


class _MarkdownErrorTable:
    bbox = (72.0, 130.0, 382.0, 214.0)
    row_count = 2
    col_count = 2

    def to_markdown(self, *, clean: bool = False, fill_empty: bool = True) -> str:
        raise RuntimeError("kaboom")


class _DoubleFailTable:
    """Rejects keyword args, then fails the no-arg ``to_markdown()`` fallback."""

    bbox = (72.0, 130.0, 382.0, 214.0)
    row_count = 2
    col_count = 2

    def to_markdown(self, *args: object, **kwargs: object) -> str:
        if kwargs:
            raise TypeError("unexpected keyword argument")
        raise RuntimeError("boom")


class _BadBboxTable(_FakeTable):
    bbox = (1.0, 2.0, 3.0)  # malformed: not a 4-tuple
