# HANDOFF

## Current objective
Review the uncommitted 0.3.0 peer-section boundaries and text-integrity correction with parent PRAI.
No publication, commit or push.

## Completed in this session
- Numbered families now nest below a recurring intermediate parent (Part >
  Chapter > "Exercise N:"); one-off covers and diagram letters never qualify.
  Four-tier PDF regression + cover/diagram guard; full suite 665 passed (5.90 s).
  Seed PDFs re-convert byte-identically (body + removed-blocks) to the accepted run.
- Current follow-up preserves larger Part parents and smaller Chapter/Annex
  subsections: equal-size peers only, map rebalanced below promoted families.
  Two real generated-PDF regressions cover Parts/Chapters and the two-font
  Annex/Water safety/Boiling collision. Current full suite663 passed6.16s.
- Correct minor version 0.2.0 for default min_text_len=1 and new audit artifacts;
  changelog describes changes since 0.1.3, not unreleased intermediate fixes.
- Owner approved restored audited furniture filtering: exact repeated outer
  margin labels/navigation and consistent page sequences across >=3 pages.
  No normalization of embedded digits, changing Step N headings or Roman units.
- Default-length and margin regressions use actual generated PDF conversion.
- Full suite: 656 passed (6.07 s final replay), including side-navigation PDF regression.
- Previous follow-up suite (before changelog consolidation): 659 passed (5.97 s). Protect canonical semantic heading,
  retain numbered major-title hierarchy and demote narrative figure references.
  Warning-level text-integrity QA flags U+FFFD/unexpected controls without rewriting.
- Historical repeat: 659 passed (8.16 s), NOT final-tree proof: subsequent changelog
  consolidation broke the release assertion, reproduced by review (658/1).
  Corrected assertion and previous Slice4 suite: 661 passed (5.95 s).
  Unreleased intermediate 0.2.x changelog
  sections folded into single draft 0.3.0, describing changes from HEAD 0.1.3.
- Parent rebuilt three pinned research PDFs through its existing CLI with
  light audit (no model/judge). New pack has 7671 chunks and 1389 image links.
  Audit: construction 71, handbook 0, workbook 351 (106 side navigation strips).
  Parent inspects removed text/geometry; no silent content deletion claim.
- New parent rebuild keeps the same counts/audit hashes, corrects Module 2
  section paths, and flags 473 workbook chunks for source review (51 U+FFFD).
  Pack is research-only, not cleared for release. Batch/SSE producing-path test passes.
- Current peer-section fix ends module inheritance at same/larger non-family
  headings, including Skills/Glossary. Promotion binds block IDs, not text;
  smaller identical TOC lines and single-letter diagram labels are not promoted.
  Running-only copies with uniform typography are not protected just because
  classified as headings. Larger genuine title in same margin band still retained.
- Parent final rebuild 71d67892...71a6c8 retains 7671 chunks/1389 images;
  Skills/Glossary no longer inherit Module 5. 473 corruption warnings persist.

## Current status
Uncommitted module source/tests/docs are intended. Parent signed releases and
original PDFs untouched. This does NOT establish complete original PDF
extraction, pixel/layout equivalence, or new-pack client/device certification.
Furniture detection remains a heuristic; every removal must be inspected before
release, especially repeated real headings near margins. Prior empty-audit
8093-chunk result was furniture-polluted and is superseded, not a clean result.
Previous 0.1.4 and 7777-chunk records are superseded, not release evidence.

## Next step
Owner review of parent integration; all-pack rebuild and client proofs remain
with PRAI. Owner decision pending: whether to lift the three-level typography
map cap (fourth heading size currently shares level 3 when no numbered family is
promoted); it changes default output for many PDFs. Do not publish, commit or push.

## Important files
- CHANGELOG.md
- pyproject.toml
- src/anydoc2md/format_converters/_pdf_page_furniture.py
- src/anydoc2md/format_converters/_pdf_heading_roles.py
- src/anydoc2md/output_qa/text_integrity.py
- tests/test_pdf_preservation.py
- docs/progress/20261118.md

## Notes for next session
Read AGENTS.md. Preserve unrelated existing edits. No network/private corpus
or binary fixture added; tests generate tiny PDFs. Parent logs and rebuilt
packs remain ignored under its .ui-tester folder.

## Last updated
2026-11-18 06:10 UTC
