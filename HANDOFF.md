# HANDOFF

## Current objective

Slice 8A, the fixed-output stale-file guard plus its current-run trust predicate, is complete. (Slice 8, the staging helper, is committed in `ba0898f`.)

## Completed in this session

- Added `paragraph_repair_candidate_is_current(adapter_staging_dir) -> bool` to `paragraph_repair/application.py`: trusts a candidate only when `index_paragraph_repaired.md`, a well-formed sidecar written by this helper (`created_by` check), and `index.md` are all present and **both** recorded fingerprints verify — the sidecar's raw-input SHA-256 matches the current `index.md` and its output SHA-256 matches the on-disk repaired file (recorded artifact paths are checked too). Read-only.
- Exported the predicate from `paragraph_repair.__init__`.
- Added `src/anydoc2md/staging_hygiene.py` with `prepare_adapter_fixed_output_slot(adapter_staging_dir)`: removes `index_fixed.md` unconditionally, removes paragraph-repair artifacts only when they are not a trusted current-run candidate, preserves all raw adapter output, touches nothing outside the directory, and clears the slot whether it is a file, symlink (unlinked, not followed), or directory. No-op on a missing or clean directory.
- Wired the guard into the orchestrator as Stage 2.3, per adapter dir with `index.md`, immediately before `apply_fix_extensions(...)`.
- Added `tests/test_staging_hygiene.py` (11 tests), 10 trust-predicate tests in `tests/test_paragraph_repair_staging_application.py` (now 20), and a Stage 2.3 integration test in `tests/test_tournament_orchestrator.py`.
- Addressed red-team findings: wired the guard into production (an unused helper did not meet 8A's goal and left a real stale-publish bug when no fix files exist), added output-integrity verification to the predicate, and made removal type-agnostic.
- Verified: guard tests 11 passed, staging-application tests 20 passed, full suite 580 passed.

## Current status

The stale-file guard is now **wired** into the tournament orchestrator (Stage 2.3): on a rerun into a reused staging dir, a stale `index_fixed.md` (and a non-current paragraph-repair candidate) is cleared before selection/publishing. This aligns with documented "rerun overwrites previous result" semantics; raw adapter output, CLI arguments, and public result shape are unchanged, and fresh/clean runs are unaffected (the guard is a no-op).

Paragraph repair itself remains unwired: no orchestration stage runs `apply_paragraph_continuity_repair(...)`, and no published output path consumes `index_paragraph_repaired.md`. The in-memory pipeline, the single-adapter staging helper, the stale-file guard (now wired), and the trust predicate exist as the building blocks Slices 9–10 compose.

## Next step

Implement Slice 9: update `apply_fix_extensions(...)` so project-local fixes build on a trusted current-run candidate (decided by `paragraph_repair_candidate_is_current`) instead of discarding it, while preserving exact current behavior when no trusted candidate exists. Slice 10 then adds Stage 2.4 (run paragraph repair) and the composition that promotes a current-run candidate into `index_fixed.md`.

## Important files

- `docs/progress/20260527.md` (master SABRE plan; see "Slice 8 — Add staging-dir application helper")
- `docs/progress/20260609.md`
- `src/anydoc2md/staging_hygiene.py`
- `src/anydoc2md/fix_application.py` (the existing `index_fixed.md` owner Slice 9 must update)
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/__init__.py`
- `src/anydoc2md/paragraph_repair/quality.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `src/anydoc2md/paragraph_repair/normalization.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_staging_hygiene.py`
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
- `INDEX_FIXED_MD` is defined in `staging_hygiene.py` but still duplicated as literals in `fix_application.py`, `selector.py`, and `cli.py` — minor future consolidation.
- The orchestrator returns original text on rejection and candidate text only when `decision.accepted`; `repaired_paragraph_count` describes the returned text, and `attempted` reflects `settings.enabled`.
- `accept_repair(...)` requires document-level row-sliced detection, at least one merge group, preserved structural counts, preserved content, and score improvement above `min_quality_delta`.
- `content_preserved=False` means real non-whitespace loss (hard reject); `hyphen_join_count > 0` is report evidence, not an automatic reject.
- New Slice 8A files intended for Git: `src/anydoc2md/staging_hygiene.py`, `tests/test_staging_hygiene.py` (plus edits to `application.py`, `__init__.py`, `orchestrator.py`, `tests/test_paragraph_repair_staging_application.py`, and `tests/test_tournament_orchestrator.py`).

## Last updated

2026-06-09 12:29 UTC
