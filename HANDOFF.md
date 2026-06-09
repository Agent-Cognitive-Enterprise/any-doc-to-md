# HANDOFF

## Current objective

Slice 8B, stale raw adapter-output cleanup on failed reruns, is complete. Slice 8A is committed in `0633c7e`; Slice 8 is committed in `ba0898f`.

## Completed in this session

- Added `prepare_adapter_run_output_slot(adapter_staging_dir)` to `staging_hygiene.py`: before each adapter run, clears known generated conversion artifacts from that adapter dir (`index.md`, `images/`, `image_dimensions.json`, `adapter_result.json`, `index_fixed.md`, and stale/untrusted paragraph-repair artifacts) while preserving unrelated files.
- Added `clear_failed_adapter_output(adapter_staging_dir)`: after a non-success adapter result, removes selectable/publishable artifacts while preserving a current `adapter_result.json` failure sidecar when present.
- Wired `run_tournament(...)` to prepare the output slot before loading/running an adapter, clear output before creating error results for import/unhandled adapter exceptions, clear output after returned non-success results, and clear output before timeout error results. Failed-result cleanup and reporting target the runner-assigned adapter dir, not a path echoed back by a faulty adapter result.
- Added runner regression tests for stale prior output on failed rerun, partial current output from failed adapter, bad returned staging paths, import failure with stale prior output, timeout cleanup, and successful rerun that must not keep stale images.
- Recorded the Slice 8B progress entry.
- Verified: runner/staging/orchestrator focused tests 33 passed, full suite 585 passed.

## Current status

The tournament runner now prevents stale raw adapter output from surviving failed reruns. A dirty adapter staging dir no longer passes hard gates through a prior-run `index.md` when the current adapter import/run fails or times out, and successful reruns start from a clean generated-output slot so old images are not carried forward. Wall-clock-timeout outputs are discarded even if the adapter thread later completes before the runner returns.

Paragraph repair itself remains unwired: no orchestration stage runs `apply_paragraph_continuity_repair(...)`, and no published output path consumes `index_paragraph_repaired.md`. The in-memory pipeline, the single-adapter staging helper, the stale-file guards, and the trust predicate exist as the building blocks Slices 9–10 compose.

## Next step

Implement Slice 9: update `apply_fix_extensions(...)` so project-local fixes build on a trusted current-run candidate (decided by `paragraph_repair_candidate_is_current`) instead of discarding it, while preserving exact current behavior when no trusted candidate exists. Slice 10 then adds Stage 2.4 (run paragraph repair) and the composition that promotes a current-run candidate into `index_fixed.md`.

## Important files

- `docs/progress/20260527.md` (master SABRE plan; see "Slice 8 — Add staging-dir application helper")
- `docs/progress/20260609.md`
- `src/anydoc2md/staging_hygiene.py`
- `src/anydoc2md/format_converters/tournament/runner.py`
- `src/anydoc2md/fix_application.py` (the existing `index_fixed.md` owner Slice 9 must update)
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/__init__.py`
- `src/anydoc2md/paragraph_repair/quality.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `src/anydoc2md/paragraph_repair/normalization.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_staging_hygiene.py`
- `tests/test_tournament_runner.py`
- `tests/test_paragraph_repair_staging_application.py`
- `tests/test_paragraph_repair_application.py`
- `tests/test_paragraph_repair_quality.py`

## Notes for next session

- `repair_markdown_paragraph_continuity(...)` is the in-memory entry point and does no file I/O.
- `apply_paragraph_continuity_repair(...)` is the single-adapter staging helper. It writes `index_paragraph_repaired.md` and `paragraph_repair_report.json` only on acceptance, and never modifies raw `index.md`.
- `index_fixed.md` remains owned by the existing tournament fix/publish path. Paragraph repair does not touch it.
- `paragraph_repair_report.json` includes raw/repaired fingerprints, `owns_output=True`, and `publishes_index_fixed=False`.
- The helper clears only its own stale paragraph-repair artifacts on rejected/disabled/missing-input runs.
- `paragraph_repair_candidate_is_current(...)` is the single source of trust for Slices 9 and 10. It requires both `index_paragraph_repaired.md` and `paragraph_repair_report.json` present, this helper's `created_by`, the raw-input SHA-256 to match the current `index.md`, **and** the recorded output SHA-256 to match the on-disk repaired file (so a corrupted/swapped repaired file is rejected).
- `prepare_adapter_fixed_output_slot(...)` is the Slice 8A guard, now wired as orchestrator Stage 2.3 (per adapter dir with `index.md`, before `apply_fix_extensions(...)` and selection). `index_fixed.md` removal is unconditional by design (no ownership manifest exists for that slot) and clears file/symlink/directory; Slice 10 will insert Stage 2.4 (paragraph repair) between the guard and fix extensions.
- `prepare_adapter_run_output_slot(...)` and `clear_failed_adapter_output(...)` are the Slice 8B runner guards. They clear known generated artifacts only and preserve unrelated files in adapter staging dirs.
- Selector/orchestrator consumers still primarily inspect disk state rather than `AdapterResult.status`. Slice 8B aligns disk state for normal in-process runner executions, but direct `select_candidate(...)` calls or a process crash/SIGKILL between adapter output creation and cleanup can still observe stale disk state. Consider a future hardening slice that gates selection by successful current-run `AdapterResult`s.
- `INDEX_FIXED_MD` is defined in `staging_hygiene.py` but still duplicated as literals in `fix_application.py`, `selector.py`, and `cli.py` — minor future consolidation.
- The orchestrator returns original text on rejection and candidate text only when `decision.accepted`; `repaired_paragraph_count` describes the returned text, and `attempted` reflects `settings.enabled`.
- `accept_repair(...)` requires document-level row-sliced detection, at least one merge group, preserved structural counts, preserved content, and score improvement above `min_quality_delta`.
- `content_preserved=False` means real non-whitespace loss (hard reject); `hyphen_join_count > 0` is report evidence, not an automatic reject.
- Slice 8B files intended for Git: edits to `src/anydoc2md/staging_hygiene.py`, `src/anydoc2md/format_converters/tournament/runner.py`, `tests/test_tournament_runner.py`, `docs/progress/20260609.md`, and `HANDOFF.md`.

## Last updated

2026-06-09 23:10 UTC
