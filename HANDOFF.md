# HANDOFF

## Current objective

Implement the table-fidelity branch in SABRE slices. Target behavior is native
Markdown table preservation in the fast `inhouse` PDF path using PyMuPDF table
APIs, with no heavy optional converter added to the default path.

## Completed in this session

- Created `docs/progress/20260612.md` for the new
  `correct-tables-conversion` branch.
- Recorded the planning-only table-fidelity objective, constraints, proposed
  test texts, and first SABRE slice.
- Updated the planning note after red-team review to clarify that synthetic PDF
  fixtures must draw ruled grid tables with plain cell text, not literal pipe
  characters.
- Confirmed the branch was clean before creating the progress file.
- Verified current code shape at a high level: PDF conversion is currently
  text/image only, existing pipe-looking text tables are emitted as fenced code,
  and document overrides already provide a compatible opt-out mechanism.
- Implemented Slice 1: added `TableBlock`, made the PDF assembler accept
  optional table blocks without changing existing callers, and added a focused
  sort-order test.
- Fixed Slice 1 review findings: explicit table blocks now suppress overlapping
  flattened text in the assembler, `Table N.` captions attach to same-page table
  blocks, and tests cover no-op empty table blocks, native table rendering,
  caption placement, and duplicate suppression.
- Fixed a follow-up review finding: captions are only relocated to hug an image
  or table when they are already adjacent to it in reading order. A caption
  separated from its target by intervening body text now stays in its natural
  position instead of leapfrogging that text. Covered by a new regression test.
- Implemented Slice 2: added isolated PyMuPDF page-table extraction helper and
  focused tests, without wiring it into full PDF conversion.
- Applied red-team residual fixes to Slice 2: removed the unused
  `TableBlock.warning` field (per-table problems are surfaced through the
  helper's returned warnings list, not on the block), loosened the brittle
  exact-bbox test assertion to a 1pt tolerance, and added branch tests for the
  undersized-table filter, non-int dimensions, `to_markdown` failures (direct
  and no-arg fallback), and malformed-bbox handling.

## Current status

Slice 2 is implemented and tested. A page-level table extraction helper exists,
but it is not wired into `pdf_converter` yet. No CLI behavior, converter
behavior, staging shape, or default output contract has changed.

## Next step

Slice 2 red-team review is done and its residual fixes are applied. Next,
implement Slice 3: `PdfExtractionResult` / `extract_pdf_blocks_v2(...)` plus PDF
converter wiring, while preserving the old `extract_pdf_blocks()` two-tuple
behavior.

## Important files

- `docs/progress/20260612.md`
- `src/anydoc2md/format_converters/_pdf_blocks.py`
- `src/anydoc2md/format_converters/_pdf_assemble.py`
- `src/anydoc2md/format_converters/_pdf_extract.py`
- `src/anydoc2md/format_converters/_pdf_tables.py`
- `src/anydoc2md/format_converters/pdf_converter.py`
- `tests/test_pdf_converter_refactor.py`
- `tests/test_pdf_tables.py`

## Notes for next session

- Do not make table extraction default-on before duplicate flattened text
  suppression is implemented.
- First implementation scope is PyMuPDF-detected tables, especially ruled grid
  tables. Borderless aligned tables remain out of scope until a later slice
  explicitly changes and tests the `find_tables(...)` strategy.
- Keep existing `extract_pdf_blocks()` two-tuple compatibility.
- Prefer generated synthetic PDF fixtures in tests; a local PyMuPDF probe during
  planning recognized a simple drawn grid table and produced native Markdown.
  Fixtures should draw grid lines and insert plain cell text; do not insert
  literal pipe-delimited table text.
- When PyMuPDF emits a `TableBlock`, it should take precedence over overlapping
  flattened text. When PyMuPDF detects no table, the existing literal-pipe
  `block_kind == "table"` fenced-code fallback stays unchanged unless a separate
  slice changes it deliberately.
- Planned opt-out key: `table_extraction: off`.
- The prior 0.1.3 release handoff recorded TestPyPI/production publishing as
  not run. That release work is deliberately deferred outside this table branch
  unless the maintainer says it has been completed.
- Slice 1 verification:
  - `python -m py_compile src/anydoc2md/format_converters/_pdf_blocks.py src/anydoc2md/format_converters/_pdf_assemble.py tests/test_pdf_converter_refactor.py`: passed.
  - `python -m pytest tests/test_pdf_converter_refactor.py -q`: 8 passed.
  - `python -m pytest -q`: 652 passed.
  - `git diff --check`: passed.
- Slice 2 verification (including red-team residual fixes):
  - `python -m py_compile src/anydoc2md/format_converters/_pdf_tables.py tests/test_pdf_tables.py`: passed.
  - `python -m pytest tests/test_pdf_tables.py -q`: 16 passed.
  - `python -m pytest tests/test_pdf_tables.py tests/test_pdf_converter_refactor.py -q`: 24 passed.
  - `python -m pytest -q`: 668 passed.
  - `git diff --check`: passed.

## Last updated

2026-06-12 05:04 UTC
