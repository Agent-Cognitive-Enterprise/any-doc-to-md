# HANDOFF

## Current objective

Slice 12 is complete in the working tree: paragraph fragmentation now has QA/scoring visibility, building on the completed Slice 10 paragraph-repair integration and red-team residual fix.

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
- Added `check_paragraph_not_row_sliced(...)` as a Layer 1 QA warning that reuses the paragraph repair detector and emits only bounded numeric signal details plus sample line numbers.
- Registered the new QA check in `run_all(...)` and added a modest `paragraph_not_row_sliced` score weight of `1.5`.
- Fixed the Slice 12 scoring review finding by adding an explicit `DOCUMENT_LEVEL_CHECK_MULTIPLIERS["paragraph_not_row_sliced"] = 2`, so diagnostic detail count no longer controls the penalty.
- Added an optional `ParagraphRepairSettings` parameter to `check_paragraph_not_row_sliced(...)` and a regression proving custom settings can tighten detection.
- Resolved the follow-up review finding that this parameter was untyped and inert in the pipeline: typed it as `ParagraphRepairSettings | None`, documented that the QA warning is intentionally independent of `--paragraph-repair` (the tournament always scores with defaults, so `off` reports fragmentation without auto-fixing and never silences the penalty), and pinned it with `test_warning_is_independent_of_repair_mode`.
- Reverted a collateral trailing-whitespace edit that had stripped Markdown hard breaks from the two pre-existing Slice 10 progress entries.
- Loosened brittle paragraph-fragmentation tests away from exact fixture signal values.
- Documented the detector's Latin-script/lowercase heuristic bias in the spec and troubleshooting guide.
- Added selector coverage proving a clean eligible adapter beats an unrepaired row-sliced adapter by score.
- Updated README, the tournament spec, and troubleshooting docs for the new warning and current repair/fix/QA ordering.
- Recorded the Slice 10 progress entry in `docs/progress/20260610.md`.
- Recorded the Slice 12 progress entry in `docs/progress/20260610.md`.
- Verified after Slice 12 review fix: focused QA/scoring/selector tests 98 passed; tournament/fix/public-benchmark tests 43 passed; combined paragraph-repair/output-QA/scoring/selector selection 229 passed, 394 deselected; full suite 623 passed.

## Current status

Default `run_full_tournament(...)` now creates and composes trusted paragraph-repair candidates when the deterministic quality gate accepts them, including the committed 13-fragment `row-sliced-note.txt` fixture. Raw adapter `index.md` remains preserved; `index_fixed.md` remains the selected/published improved-output slot; `TournamentResult.to_dict()` shape is unchanged. If row-sliced Markdown remains unrepaired, QA emits a warning and scoring applies an explicit 6-point document-level penalty.

## Next step

Run a SABRE red-team review before committing. High-risk review areas: the lower default repair floor, short-document false positives, the explicit 6-point QA warning penalty, language-uneven detector behavior, bounded-detail privacy, public benchmark fixture semantics, opt-out correctness, stale artifact handling, CLI/API compatibility, and selector/publisher/audit consistency.

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
- `src/anydoc2md/output_qa/checks.py`
- `src/anydoc2md/output_qa/runner.py`
- `src/anydoc2md/output_qa/scoring.py`
- `tests/test_output_qa_paragraph_fragmentation.py`
- `tests/test_selector.py`
- `README.md`
- `docs/benchmark-reproduction.md`
- `docs/specs/multi-method-converter-tournament.md`
- `docs/agent-conversion-guide.md`
- `docs/troubleshooting.md`
- `docs/progress/20260610.md`
- `examples/benchmark-corpus/row-sliced-note.txt`
- `.gitignore`

## Notes for next session

- `paragraph_repair="auto"` is default-enabled, local, deterministic, and no-network.
- `paragraph_repair="off"` intentionally invokes `apply_paragraph_continuity_repair(..., settings=ParagraphRepairSettings(enabled=False))` instead of merely skipping repair, so owned stale repair artifacts are cleared before `apply_fix_extensions(...)`.
- `apply_fix_extensions(...)` is still the only writer of `index_fixed.md`; paragraph repair writes only `index_paragraph_repaired.md` and its sidecar.
- The first Slice 10 implementation deliberately avoids adding repair reports to `TournamentResult`; sidecar reports are the evidence surface.
- The CLI option exposes only `auto` and `off`; threshold tuning remains private.
- `paragraph_not_row_sliced` is a soft QA warning, not a hard gate. Its details are numeric and line-number only, and scoring ignores diagnostic detail count via an explicit document-level multiplier. The warning is independent of `--paragraph-repair`: it always scores with default thresholds, so `off` surfaces fragmentation rather than silencing it. Do not thread repair settings into QA scoring.
- `BIBLE.md` was intentionally ignored per the latest user instruction.
- Full suite is green at 624 tests after the Slice 12 repair-mode-independence review fix.

## Last updated

2026-06-10 02:01 UTC
