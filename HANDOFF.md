# HANDOFF

## Current objective

Fix the residual red-team finding: separate the document-level `content_preserved` taint into an honest loss guard plus an explicit hyphen-ambiguity count.

## Completed in this session

- Reviewed sibling project `AGENTS.md` and `HANDOFF.md` patterns under `/home/user/PycharmProjects/`.
- Reviewed the local SABRE reference used by sibling projects.
- Read ADTM `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, and the canonical tournament spec context before editing.
- Updated `AGENTS.md` to require reading `HANDOFF.md` when present and creating it when missing before ending change-producing work.
- Added a `HANDOFF.md` section structure and maintenance rules to `AGENTS.md`.
- Clarified the SABRE acronym and connected SABRE progress files to `HANDOFF.md` as historical record versus current-state snapshot.
- Created this root `HANDOFF.md`.
- Recorded this process slice in `docs/progress/20260609.md`.
- Verified the tracked `AGENTS.md` diff with `git diff --check -- AGENTS.md`.
- Checked trailing whitespace across the changed process Markdown files with `rg -n "[[:blank:]]$" AGENTS.md HANDOFF.md docs/progress/20260609.md`; no matches.
- Added direct repairer regression coverage in `tests/test_paragraph_repair_repairer.py`.
- Tightened `repair_blocks()` so pair-level continuation matches are only rewritten when the collected run reaches `min_continuation_run_blocks`.
- Updated the repairer's content-preservation normalization so safe discretionary hyphen joins can still be treated as content-preserving.
- Clarified `AGENTS.md` so read-only Q&A and red-team review can remain read-only without mutating `HANDOFF.md`.
- Recorded the red-team fix slice in `docs/progress/20260609.md`.
- Verified targeted paragraph-repair tests: `75 passed`.
- Verified the full default suite: `525 passed`.
- Verified tracked diff whitespace with `git diff --check`.
- Checked trailing whitespace across changed tracked and untracked process/repairer files; no matches.
- Changed paragraph-repair hyphen joins to preserve the hyphen instead of deleting it.
- Restored `content_preserved` to a strict whitespace-token comparison without de-hyphenation normalization.
- Added regressions for wrapped compounds such as `state-of-the-art`, `well-known`, and `long-term`.
- Added a `content_preserved=False` regression through the repairer path.
- Added `pair_is_continuation()` as the clearer pair-level API and kept `should_merge()` as a documented compatibility alias.
- Reduced repeated rescans by advancing past collected short near-runs instead of re-walking them one block at a time.
- Verified the full default suite after the hyphen-evidence fix: `526 passed`.
- Redefined `RepairDraft.content_preserved` as a whitespace-insensitive character round-trip (true loss guard); it stays `True` for character-preserving hyphen joins and flips `False` only on real content loss such as the old hyphen-dropping bug.
- Added `RepairDraft.hyphen_join_count` so the ambiguity of collapsed end-of-block hyphen boundaries is reported orthogonally instead of tainting the whole-document boolean.
- Added a direct `_content_preserved` guard test and an orthogonality test proving a clean run keeps `content_preserved=True` even when a hyphen run shares the document.
- Documented the `_merge_group` right-edge invariant that makes recomputing the join kind safe.
- Verified the full default suite after the orthogonal-evidence fix: `528 passed`.

## Current status

The follow-up red-team findings are addressed and the default test suite passes. No CLI behavior, package metadata, dependencies, converter adapters, scoring, staging integration, or output shape has been changed.

Paragraph repair remains an internal, in-memory implementation slice. It is not wired into tournament orchestration or final published output.

## Next step

Review or implement the paragraph-repair quality gate as the next useful slice if paragraph continuity repair remains the active workstream.

## Important files

- `AGENTS.md`
- `HANDOFF.md`
- `docs/progress/20260609.md`
- `docs/progress/20260527.md`
- `src/anydoc2md/paragraph_repair/model.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `tests/test_paragraph_repair_model.py`
- `tests/test_paragraph_repair_repairer.py`

## Notes for next session

- `HANDOFF.md` is the current-state bridge, not a changelog or diary.
- For change-producing SABRE tasks, use `docs/progress/YYYYMMDD.md` for the historical slice record and keep this file focused on the current repo state.
- The default ADTM behavior remains local, deterministic, and cost-free.
- `HANDOFF.md`, `docs/progress/20260609.md`, `src/anydoc2md/paragraph_repair/repairer.py`, and `tests/test_paragraph_repair_repairer.py` are intended to be tracked.
- `repair_blocks()` now guards against isolated two-block rewrites by requiring a merge group of at least `min_continuation_run_blocks`; pair-level `pair_is_continuation()` and the `should_merge()` alias can still return true for diagnostic use.
- Ambiguous hyphenated joins preserve the hyphen and keep `content_preserved=True` (no characters lost); the count of such joins is reported via `RepairDraft.hyphen_join_count` for a downstream quality gate to scrutinize. A future gate should treat `content_preserved=False` as real loss (reject) and use `hyphen_join_count > 0` as the review signal.

## Last updated

2026-06-09 05:51 UTC
