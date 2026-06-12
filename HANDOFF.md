# HANDOFF

## Current objective

Implement the table-fidelity branch in SABRE slices. Target behavior is native
Markdown table preservation in the fast `inhouse` PDF path using PyMuPDF table
APIs, with no heavy optional converter added to the default path.

## Completed in this session

- Created and maintained `docs/progress/20260612.md` for the
  `correct-tables-conversion` branch.
- Implemented Slice 1: added `TableBlock`, optional assembler table plumbing,
  native table formatting, table-aware caption placement, and duplicate
  flattened-text suppression when explicit table blocks are supplied.
- Implemented Slice 2: added isolated PyMuPDF page-table extraction helper in
  `_pdf_tables.py`, including Markdown-shape validation and nonfatal warnings.
- Applied Slice 2 review fixes: removed dead per-table warning state and added
  branch coverage for malformed/undersized tables and `to_markdown()` failures.
- Implemented Slice 3: added `PdfExtractionResult` and
  `extract_pdf_blocks_v2(...)`, preserved the old `extract_pdf_blocks()`
  two-tuple wrapper, and wired table blocks into `pdf_converter.convert(...)`.
- Made in-house PDF conversion emit PyMuPDF-detected ruled tables as native
  Markdown by default, with `table_extraction: off` as a per-document opt-out.
- Fixed the YAML compatibility bug where unquoted `table_extraction: off` loads
  as boolean `False`; extraction mode normalization now treats `False` as off.
- Applied Slice 3 review fixes: converter warnings now flow through the
  in-house adapter into `AdapterResult` / `adapter_result.json`, Markdown table
  validation checks row widths before creating suppressing `TableBlock`s, and
  the private `_extract` facade alias has the expected lint suppression.
- Implemented Slice 4: completed the remaining planned suppression work by
  adding `table_text_suppression_overlap` as a documented per-document override
  while preserving the existing default `0.65` duplicate-text threshold.
- Updated tests and docs for the default-on table behavior and opt-out.

## Current status

Slice 4 is implemented and tested but uncommitted. Default PDF output can now
change for PyMuPDF-detected ruled tables: native Markdown tables are emitted and
overlapping flattened cell text is suppressed. Existing CLI/module calls remain
compatible, and `extract_pdf_blocks(...)` still returns the old two-tuple.

## Next step

Run SABRE red-team review of Slice 4. If no blocker is found, continue with the
next slice from the branch plan, likely the optional table extraction
report/audit evidence slice.

## Important files

- `docs/progress/20260612.md`
- `CHANGELOG.md`
- `README.md`
- `docs/adapter-guide.md`
- `docs/troubleshooting.md`
- `docs/specs/multi-method-converter-tournament.md`
- `src/anydoc2md/format_converters/_pdf_blocks.py`
- `src/anydoc2md/format_converters/_pdf_assemble.py`
- `src/anydoc2md/format_converters/_pdf_extract.py`
- `src/anydoc2md/format_converters/_pdf_tables.py`
- `src/anydoc2md/format_converters/adapters/base.py`
- `src/anydoc2md/format_converters/adapters/inhouse.py`
- `src/anydoc2md/format_converters/pdf_converter.py`
- `tests/test_converter_adapters.py`
- `tests/test_pdf_converter_refactor.py`
- `tests/test_pdf_tables.py`

## Notes for next session

- First implementation scope is PyMuPDF-detected ruled tables. Borderless
  aligned tables remain out of scope until a later slice deliberately changes
  and tests `find_tables(...)` strategy.
- When PyMuPDF emits a `TableBlock`, it takes precedence over overlapping
  flattened text. When PyMuPDF detects no table, the existing literal-pipe
  `block_kind == "table"` fenced-code fallback stays unchanged unless a
  separate slice changes it deliberately.
- No table extraction sidecar report exists yet. Slice 3 now propagates
  extraction warnings through `ConversionResult.warnings` and the in-house
  adapter's `AdapterResult.warnings`, so they are visible in
  `adapter_result.json` and top-level result JSON `adapter_results`.
- The prior 0.1.3 release handoff recorded TestPyPI/production publishing as
  not run. That release work is deliberately deferred outside this table branch
  unless the maintainer says it has been completed.
- Slice 3 verification:
  - `python -m py_compile src/anydoc2md/format_converters/_pdf_extract.py src/anydoc2md/format_converters/pdf_converter.py tests/test_pdf_tables.py`: passed.
  - `python -m pytest tests/test_pdf_tables.py tests/test_pdf_converter_refactor.py -q`: 31 passed.
  - `python -m pytest -q`: 675 passed.
  - `git diff --check`: passed.
- Slice 3 residual-fix verification:
  - `python -m py_compile src/anydoc2md/format_converters/_pdf_tables.py src/anydoc2md/format_converters/_pdf_extract.py src/anydoc2md/format_converters/pdf_converter.py src/anydoc2md/format_converters/adapters/base.py src/anydoc2md/format_converters/adapters/inhouse.py tests/test_pdf_tables.py tests/test_converter_adapters.py`: passed.
  - `python -m pytest tests/test_pdf_tables.py tests/test_converter_adapters.py tests/test_pdf_converter_refactor.py -q`: 81 passed.
  - `python -m pytest -q`: 681 passed.
  - `git diff --check`: passed.
- Slice 4 verification:
  - `python -m py_compile src/anydoc2md/format_converters/_pdf_assemble.py src/anydoc2md/format_converters/pdf_converter.py tests/test_pdf_converter_refactor.py tests/test_pdf_tables.py`: passed.
  - `python -m pytest tests/test_pdf_converter_refactor.py tests/test_pdf_tables.py tests/test_converter_adapters.py -q`: 103 passed.
  - `python -m pytest -q`: 703 passed.
  - `git diff --check`: passed.

## Last updated

2026-06-12 07:30 UTC
