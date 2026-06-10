# HANDOFF

## Current objective

Slice 10 is complete in the working tree, including the red-team residual fix: default paragraph-continuity repair is wired into tournament orchestration, has an `auto`/`off` opt-out, and now demonstrably repairs a realistic short row-sliced document through the real CLI and public benchmark pipeline.

## Completed in this session

- Added keyword-only `paragraph_repair: str = "auto"` to `run_full_tournament(...)`; existing positional and keyword callers remain compatible.
- Wired orchestrator Stage 2.4 between `prepare_adapter_fixed_output_slot(...)` and `apply_fix_extensions(...)`: accepted repair writes `index_paragraph_repaired.md` plus `paragraph_repair_report.json`, then Slice 9 composition promotes it through `index_fixed.md`.
- Added `paragraph_repair="off"` handling. Off mode calls the repair helper with disabled settings so stale paragraph-repair artifacts from a prior identical run are cleared and cannot be promoted.
- Added CLI `--paragraph-repair {auto,off}` and forwards it to `run_full_tournament(...)`.
- Added shared mode constants and `normalize_paragraph_repair_mode(...)` in `settings.py`, exported from `anydoc2md`.
- Lowered the private paragraph-repair default floor from 20 prose blocks to 8 so short but strongly row-sliced documents can reach the existing semantic and quality gates.
- Added `examples/benchmark-corpus/row-sliced-note.txt` as a package-owned public fixture that proves default repair through the real in-house/tournament path.
- Added a narrow `.gitignore` unignore for `examples/benchmark-corpus/` so new committed public fixtures are visible despite the broad `benchmark-*/` local-output ignore.
- Updated README, the canonical tournament spec, and the agent conversion guide for default repair and the opt-out.
- Updated the public benchmark reproduction guide for the current four-fixture smoke and noted that the 2026-04-27 snapshot is historical.
- Added orchestrator tests proving repair runs before selection, `off` clears a current candidate before selection, and project-local fixes still layer after repair.
- Added CLI/settings tests for default forwarding, explicit `off`, invalid CLI values, normalization, and top-level exports.
- Added detector/application/CLI/public-benchmark regressions for realistic short row-sliced repair.
- Recorded the Slice 10 progress entry in `docs/progress/20260610.md`.
- Verified: focused paragraph-repair/CLI/public-benchmark tests 80 passed; paragraph-repair-selected tests 130 passed; fix/staging/orchestrator/public-benchmark tests 74 passed; full suite 612 passed.

## Current status

Default `run_full_tournament(...)` now creates and composes trusted paragraph-repair candidates when the deterministic quality gate accepts them, including the committed 13-fragment `row-sliced-note.txt` fixture. Raw adapter `index.md` remains preserved; `index_fixed.md` remains the selected/published improved-output slot; `TournamentResult.to_dict()` shape is unchanged.

## Next step

Run another SABRE red-team review before committing. High-risk review areas: the lower default floor and short-document false positives, public benchmark fixture semantics, opt-out correctness, stale artifact handling, CLI/API compatibility, and selector/publisher/audit consistency.

## Important files

- `src/anydoc2md/format_converters/tournament/orchestrator.py`
- `src/anydoc2md/cli.py`
- `src/anydoc2md/settings.py`
- `src/anydoc2md/__init__.py`
- `src/anydoc2md/fix_application.py`
- `src/anydoc2md/staging_hygiene.py`
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_tournament_orchestrator.py`
- `tests/test_cli.py`
- `tests/test_llm_judge_decisions.py`
- `tests/test_fix_application.py`
- `tests/test_paragraph_repair_staging_application.py`
- `tests/test_staging_hygiene.py`
- `README.md`
- `docs/benchmark-reproduction.md`
- `docs/specs/multi-method-converter-tournament.md`
- `docs/agent-conversion-guide.md`
- `docs/progress/20260610.md`
- `examples/benchmark-corpus/row-sliced-note.txt`
- `.gitignore`

## Notes for next session

- `paragraph_repair="auto"` is default-enabled, local, deterministic, and no-network.
- `paragraph_repair="off"` intentionally invokes `apply_paragraph_continuity_repair(..., settings=ParagraphRepairSettings(enabled=False))` instead of merely skipping repair, so owned stale repair artifacts are cleared before `apply_fix_extensions(...)`.
- `apply_fix_extensions(...)` is still the only writer of `index_fixed.md`; paragraph repair writes only `index_paragraph_repaired.md` and its sidecar.
- The first Slice 10 implementation deliberately avoids adding repair reports to `TournamentResult`; sidecar reports are the evidence surface.
- The CLI option exposes only `auto` and `off`; threshold tuning remains private.
- `BIBLE.md` was intentionally ignored per the latest user instruction.
- Full suite is green at 612 tests after the review fix.

## Last updated

2026-06-10 01:17 UTC
