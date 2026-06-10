# HANDOFF

## Current objective

Slice 9, making project-local fix extensions build on a trusted current-run paragraph-repair candidate, is complete (working tree). Slice 8B is committed; Slice 8A is committed in `0633c7e`; Slice 8 is committed in `ba0898f`.

## Completed in this session

- Updated `apply_fix_extensions(...)` in `fix_application.py` to pick its base text via `paragraph_repair_candidate_is_current(...)`: a trusted current-run `index_paragraph_repaired.md` becomes the starting best text; otherwise the raw `index.md`, exactly as before.
- A trusted repaired base is promoted into `index_fixed.md` even when no project-local fix improves it (`improved or had_trusted_candidate`); with no fix files present, the repaired text is written straight to `index_fixed.md`.
- Project-local fixes accumulate on top of the repaired base and are scored against the repaired base score. Raw `index.md` is always restored via a `finally`, including when base scoring raises while the repaired base is staged.
- With no trusted candidate, no `index_fixed.md` is written; a stale prior-run one is now removed on **every** exit path, including no-fix-files and missing-`index.md` early returns (a pre-existing gap; production guards already masked the normal tournament path, but direct callers were exposed).
- Addressed two rounds of red-team review of Slice 9:
  - R1/P1 (pre-existing): `audit.py` rendered raw `index.md` for the judge while selection/CLI use `index_fixed.md` when present. The post-selection audit now resolves the same effective candidate Markdown (`index_fixed.md` if present, else `index.md`).
  - R1/P2: `apply_fix_extensions(...)` no-fix-files path now clears a stale `index_fixed.md` instead of leaving it, matching the docstring's ownership contract.
  - R2/P2 (type-agnostic clearing): `Path.unlink()`/`write_text()` raise on a stale `index_fixed.md` **directory**. Promoted `staging_hygiene._remove_path` → public `remove_path` and reused it; both the clear and write paths now clear the slot type-agnostically (file/symlink/directory) on every exit path.
  - R1+R2/P3: updated the spec doc write-trigger **and** the architecture-overview Stage 2/Stage 6 lines; completed the progress "Files touched" list (audit, staging_hygiene, audit test, spec).
- Residual follow-up: `apply_fix_extensions(...)` now clears a stale `index_fixed.md` slot before returning when `index.md` is missing, with file/symlink/directory regression coverage.
- Added tests: `tests/test_fix_application.py` (Slice-9 composition + parametrized file/symlink/directory clearing for no-fix and missing-index paths + write-over-directory) and 2 audit-resolution tests in `tests/test_tournament_audit.py`.
- Recorded the Slice 9 progress entry (two review rounds plus residual follow-up).
- Verified: focused fix/audit/staging tests 46 passed, orchestrator 12 passed, full suite 600 passed.

## Current status

`apply_fix_extensions(...)` now composes project-local fixes on top of a trusted built-in paragraph-repair candidate and promotes the result into `index_fixed.md`, which the selector already prefers. An untrusted/stale `index_paragraph_repaired.md` is never used as a base and cannot reach selection through this path. Raw `index.md` is preserved in all paths.

Paragraph repair is still not *run* by orchestration: no stage calls `apply_paragraph_continuity_repair(...)`, so in production no `index_paragraph_repaired.md` exists yet for Slice 9's composition to consume. Slice 9 is the consumer; Slice 10 is the producer (Stage 2.4) plus the opt-out control.

## Next step

Implement Slice 10: add orchestrator Stage 2.4 that runs `apply_paragraph_continuity_repair(...)` per adapter dir with `index.md`, between the Stage 2.3 guard and `apply_fix_extensions(...)`, so a current-run candidate exists for Slice 9 to promote. Include the tested opt-out control (no later than this slice, since repair would become default-enabled). Keep `TournamentResult` constructor backward-compatible (sidecar reports are sufficient for the first version).

## Important files

- `docs/progress/20260527.md` (master SABRE plan; see "Slice 8 — Add staging-dir application helper")
- `docs/progress/20260609.md`
- `src/anydoc2md/staging_hygiene.py`
- `src/anydoc2md/format_converters/tournament/runner.py`
- `src/anydoc2md/fix_application.py` (the `index_fixed.md` owner; updated by Slice 9 to compose a trusted repaired base)
- `src/anydoc2md/format_converters/tournament/orchestrator.py` (Slice 10 inserts Stage 2.4 here)
- `src/anydoc2md/paragraph_repair/application.py`
- `src/anydoc2md/paragraph_repair/__init__.py`
- `src/anydoc2md/paragraph_repair/quality.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `src/anydoc2md/paragraph_repair/normalization.py`
- `src/anydoc2md/paragraph_repair/model.py`
- `tests/test_staging_hygiene.py`
- `tests/test_tournament_runner.py`
- `tests/test_fix_application.py`
- `tests/test_paragraph_repair_staging_application.py`
- `tests/test_paragraph_repair_application.py`
- `tests/test_paragraph_repair_quality.py`

## Notes for next session

- `repair_markdown_paragraph_continuity(...)` is the in-memory entry point and does no file I/O.
- `apply_paragraph_continuity_repair(...)` is the single-adapter staging helper. It writes `index_paragraph_repaired.md` and `paragraph_repair_report.json` only on acceptance, and never modifies raw `index.md`.
- `index_fixed.md` is owned by the fix/publish path (`fix_application.py`). The `paragraph_repair` module never writes it; as of Slice 9, `apply_fix_extensions(...)` composes a trusted current-run repaired candidate into `index_fixed.md` (promotes it, then layers any improving project-local fixes on top).
- `paragraph_repair_report.json` includes raw/repaired fingerprints, `owns_output=True`, and `publishes_index_fixed=False`.
- The helper clears only its own stale paragraph-repair artifacts on rejected/disabled/missing-input runs.
- `paragraph_repair_candidate_is_current(...)` is the single source of trust; Slice 9 now consumes it in `apply_fix_extensions(...)`, and Slice 10's Stage 2.4 produces the candidate it checks. It requires both `index_paragraph_repaired.md` and `paragraph_repair_report.json` present, this helper's `created_by`, the raw-input SHA-256 to match the current `index.md`, **and** the recorded output SHA-256 to match the on-disk repaired file (so a corrupted/swapped repaired file is rejected).
- `prepare_adapter_fixed_output_slot(...)` is the Slice 8A guard, now wired as orchestrator Stage 2.3 (per adapter dir with `index.md`, before `apply_fix_extensions(...)` and selection). `index_fixed.md` removal is unconditional by design (no ownership manifest exists for that slot) and clears file/symlink/directory; Slice 10 will insert Stage 2.4 (paragraph repair) between the guard and fix extensions.
- `prepare_adapter_run_output_slot(...)` and `clear_failed_adapter_output(...)` are the Slice 8B runner guards. They clear known generated artifacts only and preserve unrelated files in adapter staging dirs.
- Selector/orchestrator consumers still primarily inspect disk state rather than `AdapterResult.status`. Slice 8B aligns disk state for normal in-process runner executions, but direct `select_candidate(...)` calls or a process crash/SIGKILL between adapter output creation and cleanup can still observe stale disk state. Consider a future hardening slice that gates selection by successful current-run `AdapterResult`s.
- `INDEX_FIXED_MD` is defined in `staging_hygiene.py` but still duplicated as literals in `fix_application.py`, `selector.py`, and `cli.py` — minor future consolidation.
- The orchestrator returns original text on rejection and candidate text only when `decision.accepted`; `repaired_paragraph_count` describes the returned text, and `attempted` reflects `settings.enabled`.
- `accept_repair(...)` requires document-level row-sliced detection, at least one merge group, preserved structural counts, preserved content, and score improvement above `min_quality_delta`.
- `content_preserved=False` means real non-whitespace loss (hard reject); `hyphen_join_count > 0` is report evidence, not an automatic reject.
- Slice 9 files intended for Git: edits to `src/anydoc2md/fix_application.py`, `src/anydoc2md/format_converters/tournament/audit.py`, `src/anydoc2md/staging_hygiene.py` (the `remove_path` rename), `tests/test_fix_application.py`, `tests/test_tournament_audit.py`, `docs/specs/multi-method-converter-tournament.md`, `docs/progress/20260609.md`, and `HANDOFF.md`.
- Slice 9 added a `try/finally` in `apply_fix_extensions(...)` so raw `index.md` is restored even if base scoring raises while the repaired base is staged; `improved or had_trusted_candidate` is the write gate for `index_fixed.md`, and the slot is cleared via `remove_path(...)` (type-agnostic) before any write or stale-output early return.
- `staging_hygiene.remove_path(path)` is now the public, type-agnostic single-path remover (file/symlink/directory; symlink unlinked, not followed). Reused by both staging hygiene and `fix_application.py`; prefer it over `Path.unlink()` for any slot that downstream tests with `Path.exists()`.

## Last updated

2026-06-10 00:14 UTC
