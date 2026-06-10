# HANDOFF

## Current objective

Slice 16 closure hardening is complete in the working tree: branch-level review found and fixed two residual robustness gaps, one in paragraph-repair owned-artifact cleanup and one in tournament runner wall-clock timeout shutdown. Follow-up review deduplicated cleanup onto `path_hygiene.remove_path`, made timeout notes precise, and hardened the shared remover against concurrent timeout/pre-run cleanup races.

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
- Added `tests/test_paragraph_repair_e2e.py` using the real CLI path and committed row-sliced public fixture to prove default repair publishes `index_fixed.md` while raw adapter `index.md` remains row-sliced, and `--paragraph-repair off` publishes raw output while still reporting the soft QA penalty.
- Fixed the Slice 14 review finding by changing the off-mode e2e assertion from exact `6.0` to a positive-penalty assertion, and added comments documenting the intentional staging-layout and fixture blank-line coupling.
- Updated README, the tournament spec, and troubleshooting docs for the new warning and current repair/fix/QA ordering.
- Recorded the Slice 10 progress entry in `docs/progress/20260610.md`.
- Recorded the Slice 12 progress entry in `docs/progress/20260610.md`.
- Recorded the Slice 14 progress entry in `docs/progress/20260610.md`.
- Verified after Slice 14 review fix: new e2e tests 2 passed; CLI/public-benchmark/e2e tests 28 passed; combined paragraph-repair/output-QA/scoring/selector/CLI selection 273 passed, 353 deselected; repair/tournament/public/e2e tests 76 passed; full suite 626 passed.
- Moved `CheckResult` into `src/anydoc2md/output_qa/result.py` while preserving the existing `anydoc2md.output_qa.checks.CheckResult` import path.
- Added optional structured QA issue metadata fields (`violation_type`, `severity`, `confidence`) and explicit built-in warning/failure metadata at the check return sites.
- Kept pass results and source/dependency skip warnings legacy-shaped; removed the constructor-side default metadata map and detail-gate special case.
- Split source-fidelity checks into `src/anydoc2md/output_qa/source_checks.py` and re-exported them from `checks.py` so existing imports remain compatible.
- Added result-model tests proving legacy serialization, structured metadata, name-collision non-inheritance, skip-warning exclusion, real source-fidelity metadata, and scoring independence.
- Removed the unused `asdict` import from `output_qa/runner.py`.
- Updated README, the tournament spec, and learning-loop docs for the additive metadata and the fact that scoring still uses per-check/status weights.
- Recorded the Slice 15 progress entry in `docs/progress/20260610.md`.
- Recorded the Slice 15 review-fix progress entry in `docs/progress/20260610.md`.
- Verified after Slice 15 review fix: focused QA/scoring/selector tests 106 passed; adjacent QA/extension/CLI tests 146 passed; full suite 633 passed.
- Fixed paragraph-repair helper cleanup so stale owned artifacts that are directories are removed instead of crashing direct helper calls.
- Fixed tournament runner wall-clock timeout shutdown so `run_tournament(...)` returns a timeout result without waiting for a blocked adapter thread to finish.
- Added regressions for stale owned artifact directories and for timeout return before adapter release. The owned-artifact directory regression lives in its own focused test file so `test_paragraph_repair_staging_application.py` does not grow further.
- Recorded the Slice 16 progress entry in `docs/progress/20260610.md`.
- Verified Slice 16: repair staging/hygiene/fix tests 59 passed; tournament runner tests 11 passed; combined affected suite 112 passed; full suite 635 passed.
- Review follow-up: extracted the duplicated file/symlink/directory removal branch into a dependency-free `path_hygiene.remove_path` and reused it in `_remove_owned_artifacts` and `staging_hygiene` (the inline copy only existed because `staging_hygiene` imports from `paragraph_repair.application`, blocking a direct import back). Dropped the now-unused `import shutil` from both modules.
- Added `tests/test_path_hygiene.py` covering files, recursive directories, symlinks to files and directories, and broken symlinks; corrected the runner timeout notes to record the cleanup race and interpreter-exit join.
- Re-verified after the follow-up: affected repair/hygiene/runner tests 76 passed; full suite 641 passed.
- Fixed the concurrent cleanup race found during compatibility review: if another cleanup path removes a directory between `remove_path(...)`'s node-type probe and `shutil.rmtree(...)`, `FileNotFoundError` is now treated as a successful cleanup result while non-missing errors still propagate.
- Added a deterministic `tests/test_path_hygiene.py` regression for concurrent directory removal and re-ran the default suite: 642 passed.
- Final PR-hardening pass found one stale spec module-map line that still described `CheckResult` metadata as future work in `output_qa/checks.py`; updated it to match the current `output_qa/result.py`, `checks.py`, `source_checks.py`, `scoring.py`, and `runner.py` ownership.
- Re-ran final gates after the spec alignment: `git diff --check` clean; full suite 642 passed.

## Current status

Default `run_full_tournament(...)` now creates and composes trusted paragraph-repair candidates when the deterministic quality gate accepts them, including the committed 13-fragment `row-sliced-note.txt` fixture. Raw adapter `index.md` remains preserved; `index_fixed.md` remains the selected/published improved-output slot. If row-sliced Markdown remains unrepaired, QA emits a warning and scoring applies an explicit 6-point document-level penalty. CLI e2e coverage proves both `auto` and `off` behavior. Built-in QA issue results now add structured metadata in their check payloads, but scoring uses only check/status/detail data. Final PR-hardening checks are green at 642 tests; the remaining working-tree diff is documentation/handoff only.

## Next step

Commit the final PR-hardening documentation/handoff update, then open or update the PR. Release notes should explicitly call out that default output may change by paragraph whitespace/boundaries, while existing CLI/module calls remain compatible and `--paragraph-repair off` / `paragraph_repair="off"` preserves raw adapter Markdown.

## Important files

- `src/anydoc2md/format_converters/tournament/orchestrator.py`
- `src/anydoc2md/format_converters/tournament/runner.py`
- `src/anydoc2md/cli.py`
- `src/anydoc2md/settings.py`
- `src/anydoc2md/__init__.py`
- `src/anydoc2md/fix_application.py`
- `src/anydoc2md/staging_hygiene.py`
- `src/anydoc2md/path_hygiene.py`
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_tournament_orchestrator.py`
- `tests/test_tournament_runner.py`
- `tests/test_cli.py`
- `tests/test_llm_judge_decisions.py`
- `tests/test_fix_application.py`
- `tests/test_paragraph_repair_artifact_cleanup.py`
- `tests/test_path_hygiene.py`
- `tests/test_paragraph_repair_staging_application.py`
- `tests/test_staging_hygiene.py`
- `src/anydoc2md/output_qa/checks.py`
- `src/anydoc2md/output_qa/result.py`
- `src/anydoc2md/output_qa/source_checks.py`
- `src/anydoc2md/output_qa/runner.py`
- `src/anydoc2md/output_qa/scoring.py`
- `tests/test_output_qa_result.py`
- `tests/test_output_qa_paragraph_fragmentation.py`
- `tests/test_paragraph_repair_e2e.py`
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
- `CheckResult.to_dict()` omits `violation_type`, `severity`, and `confidence` when they are empty. Built-in warning/failure issue branches pass metadata explicitly with `issue_metadata(...)`; extension checks never inherit metadata by name collision. Scoring does not read these fields.
- `run_tournament(...)` returns a timeout result after the wall-clock guard without joining a blocked adapter thread. Two residual consequences, not zero: post-timeout `clear_failed_adapter_output(...)` runs concurrently with the still-live worker, so a late write can leave staging artifacts (bounded — the name's result is `status="timeout"` so it cannot win, and `prepare_adapter_run_output_slot(...)` re-clears the slot before the next reuse); and the worker is a non-daemon `concurrent.futures` thread, so a never-returning adapter is still joined at interpreter exit and can block process shutdown even though the call returned. Python cannot kill a running thread; full late-write isolation would require a process-level adapter execution boundary.
- `tests/test_paragraph_repair_e2e.py` is intended Git-tracked regression coverage; it creates only temporary output under pytest `tmp_path`. It intentionally inspects `.any-doc-to-md/staging/` to prove raw preservation and winner promotion.
- `BIBLE.md` was intentionally ignored per the latest user instruction.
- Full suite is green at 642 tests after the Slice 16 closure hardening, review follow-up edits, concurrent cleanup race fix, and final spec module-map alignment.

## Last updated

2026-06-10 06:34 UTC
