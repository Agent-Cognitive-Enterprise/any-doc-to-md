# HANDOFF

## Current objective

Plan the table-fidelity branch before implementation. Target behavior is native
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

## Current status

Planning only. No table extraction source code, tests, CLI behavior, converter
behavior, staging shape, or output contract has been changed yet. The only
branch files changed are planning/handoff files.

## Next step

After explicit approval, implement Slice 1: add `TableBlock`, make
`assemble_markdown(...)` accept optional table blocks without changing output
when none are supplied, update sort typing, and add a focused sort-order unit
test.

## Important files

- `docs/progress/20260612.md`
- `src/anydoc2md/format_converters/_pdf_blocks.py`
- `src/anydoc2md/format_converters/_pdf_assemble.py`
- `src/anydoc2md/format_converters/_pdf_extract.py`
- `src/anydoc2md/format_converters/pdf_converter.py`
- `tests/test_pdf_converter_refactor.py`

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
- No tests were run in this planning-only task.

## Last updated

2026-06-12 00:29 UTC
