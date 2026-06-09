# HANDOFF

## Current objective

Slice 6, paragraph-repair quality scoring and acceptance gate, is complete.

## Completed in this session

- Added `AcceptanceDecision` to the paragraph-repair model as JSON-friendly gate evidence.
- Added `src/anydoc2md/paragraph_repair/quality.py` with deterministic quality scoring, whitespace-insensitive content fingerprinting, and `accept_repair(...)`.
- Added focused quality-gate tests in `tests/test_paragraph_repair_quality.py`.
- Verified Slice 6 with targeted paragraph-repair tests and the full default suite.
- Recorded the Slice 6 progress entry in `docs/progress/20260609.md`.
- Fixed the quality-gate red-team finding by requiring the document-level row-sliced detector instead of accepting run-length evidence alone.
- Simplified `accept_repair(...)` so the candidate text comes from `draft.text`, removing the stale-candidate argument footgun.
- Added a real short-document regression proving repair drafts below the detector's `min_paragraphs` floor are rejected.
- Aligned the older Slice 6 planning note with the implemented strict detector gate and `accept_repair(...)` signature.

## Current status

Paragraph repair remains internal and unwired: no CLI behavior, tournament orchestration, staging, scoring, dependency, or output-shape behavior changed.

Implemented branch foundation now includes model/settings, Markdown block splitting, row-sliced detection, in-memory repair drafting, repairer red-team hardening, and the in-memory quality gate.

## Next step

Implement Slice 7: add the top-level in-memory repair API that orchestrates splitting, detection, repair, quality gating, and `ParagraphRepairResult` reporting without file I/O.

## Important files

- `docs/progress/20260527.md`
- `docs/progress/20260609.md`
- `src/anydoc2md/paragraph_repair/model.py`
- `src/anydoc2md/paragraph_repair/repairer.py`
- `src/anydoc2md/paragraph_repair/quality.py`
- `tests/test_paragraph_repair_model.py`
- `tests/test_paragraph_repair_repairer.py`
- `tests/test_paragraph_repair_quality.py`

## Notes for next session

- `content_preserved=False` means real non-whitespace character loss and should be a hard reject.
- `hyphen_join_count > 0` is ambiguity evidence for quality/reporting, not automatic rejection.
- `accept_repair(...)` requires document-level row-sliced detection, at least one merge group, preserved structural counts, preserved content, and score improvement above `min_quality_delta`.
- `quality.py` is internal and not called by CLI/orchestration yet.
- New tracked files for this slice: `src/anydoc2md/paragraph_repair/quality.py` and `tests/test_paragraph_repair_quality.py`.

## Last updated

2026-06-09 07:03 UTC
