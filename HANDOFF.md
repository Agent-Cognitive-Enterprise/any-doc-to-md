# HANDOFF

## Current objective

Slice 8, the non-publishing staging-directory paragraph-repair helper, is complete.

## Completed in this session

- Added `apply_paragraph_continuity_repair(adapter_name, adapter_staging_dir, source_path, *, settings=None) -> ParagraphRepairReport`.
- The helper reads `index.md`, runs `repair_markdown_paragraph_continuity(...)`, and writes `index_paragraph_repaired.md` only when repair is accepted.
- The helper does not write, overwrite, or delete the shared tournament `index_fixed.md` slot in any path.
- Accepted repairs write `paragraph_repair_report.json` with portable source/staging attribution, raw and paragraph-repaired SHA-256 fingerprints, byte sizes, `owns_output=True`, `publishes_index_fixed=False`, and the bounded repair report.
- Missing staging directories return reason `staging_dir_missing`; missing `index.md` returns reason `index_md_missing`.
- Rejected, disabled, and missing-input repairs clear this helper's own stale `index_paragraph_repaired.md`/`paragraph_repair_report.json` artifacts while preserving unrelated `index_fixed.md`.
- Exported the staging helper from `paragraph_repair.__init__`.
- Added `tests/test_paragraph_repair_staging_application.py` (10 tests) and recorded the Slice 8 progress entry.
- Addressed red-team finding: `index_fixed.md` already belongs to fix application, selector, and publisher semantics, so paragraph repair now writes a separate artifact and no longer asserts `owns_index_fixed`.
- Addressed follow-up findings: atomic writes now clean temp files when the write itself fails; disabled staging repair intentionally clears paragraph-repair-owned stale artifacts while preserving `index_fixed.md`.
- Verified after redesign: staging helper tests 10 passed, app tests 10 passed, `-k paragraph_repair` 108 passed, full suite 558 passed.

## Current status

Paragraph repair remains internal and unwired into tournament orchestration: no CLI behavior, selection, scoring, dependency, or published output-shape behavior changed.

The in-memory pipeline and one adapter-staging helper now exist. The staging helper can create `index_paragraph_repaired.md` and `paragraph_repair_report.json` for a single adapter directory, but no production orchestration path calls it yet and no published output path consumes it.

## Next step

Design the integration/composition slice. If paragraph repair is ever promoted into `index_fixed.md`, that slice must define ordering with project-local fix extensions and real ownership/stale-file validation first.

## Important files

- `docs/progress/20260527.md` (master SABRE plan; see "Slice 8 — Add staging-dir application helper")
- `docs/progress/20260609.md`
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/__init__.py`
- `src/anydoc2md/paragraph_repair/quality.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `src/anydoc2md/paragraph_repair/normalization.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_paragraph_repair_staging_application.py`
- `tests/test_paragraph_repair_application.py`
- `tests/test_paragraph_repair_quality.py`

## Notes for next session

- `repair_markdown_paragraph_continuity(...)` is the in-memory entry point and does no file I/O.
- `apply_paragraph_continuity_repair(...)` is the single-adapter staging helper. It writes `index_paragraph_repaired.md` and `paragraph_repair_report.json` only on acceptance, and never modifies raw `index.md`.
- `index_fixed.md` remains owned by the existing tournament fix/publish path. Paragraph repair does not touch it.
- `paragraph_repair_report.json` includes raw/repaired fingerprints, `owns_output=True`, and `publishes_index_fixed=False`.
- The helper clears only its own stale paragraph-repair artifacts on rejected/disabled/missing-input runs.
- Future consumers must require both `index_paragraph_repaired.md` and `paragraph_repair_report.json` before trusting a paragraph-repair candidate.
- The orchestrator returns original text on rejection and candidate text only when `decision.accepted`; `repaired_paragraph_count` describes the returned text, and `attempted` reflects `settings.enabled`.
- `accept_repair(...)` requires document-level row-sliced detection, at least one merge group, preserved structural counts, preserved content, and score improvement above `min_quality_delta`.
- `content_preserved=False` means real non-whitespace loss (hard reject); `hyphen_join_count > 0` is report evidence, not an automatic reject.
- New Slice 8 file intended for Git: `tests/test_paragraph_repair_staging_application.py`.

## Last updated

2026-06-09 11:47 UTC
