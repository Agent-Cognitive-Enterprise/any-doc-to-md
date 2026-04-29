# Changelog

All notable changes to ADTM will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

_(nothing yet)_

## 0.1.1 — 2026-04-29

### Fixed

- **TXT converter list/line preservation** — plain-text bullet lists (`- `,
  `* `, `+ `, `•`), numbered lists (`1. `, `2. `…), and field-style lines
  (`Key: Value`) are now preserved on separate lines in the generated Markdown.
  Previously all internal newlines within a blank-line-separated block were
  collapsed to a single line, destroying list structure.
  (`src/anydoc2md/format_converters/txt_converter.py`)

- **Fix-extension score guard** — the incremental fix loop now compares each
  candidate fix against the *current best score* rather than the original
  baseline, preventing a worse later fix from replacing a better earlier one.
  (`src/anydoc2md/fix_application.py`)

### Changed

- Fix extensions are now applied to **every adapter's output**, not only the
  inhouse adapter, giving all adapters an equal chance to benefit from
  project-local post-processing hooks.

- Adapter execution is **parallel by default** (`ThreadPoolExecutor`); a
  wall-clock timeout guard (`timeout_s + 15 s`) produces a `timeout` error
  result for hung adapters so the tournament always completes.

- Per-adapter timing table is printed to the CLI after conversion showing name,
  QA score, wall-clock time, and `[winner]` marker.

- CLI flags renamed for clarity: `--project-qa` → `--qa`,
  `--project-inhouse` → `--fix`, `--project-qa-all` → `--qa-all`,
  `--project-inhouse-all` → `--fix-all`. Project extension directories renamed
  `inhouse-extensions/` → `fix-extensions/`.

- `winner/` promotion now prefers `index_fixed.md` (post-fix output) over
  `index.md` when a fix extension improved the QA score.

### Added

- `src/anydoc2md/fix_application.py` — standalone per-adapter incremental fix
  loop with score-guard and `index_fixed.md` write/cleanup logic.
- `src/anydoc2md/scaffold_staging.py` — scaffold staging logic extracted from
  `cli.py`.
- `tests/test_txt_converter.py` — 12 tests covering list preservation,
  field-style line preservation, and prose collapse.
- `tests/test_fix_application.py` — 14 tests covering the score-guarded fix
  loop including the regression for the running-best comparison.

## 0.1.0 — 2026-04-23

- Initial public release. Document-to-Markdown conversion, QA checks, adapter
  tournaments, LLM-assisted audit helpers, and benchmark tooling under
  Apache-2.0. Inhouse adapter handles PDF, HTML, and TXT natively; LibreOffice
  adapter handles DOC/DOCX/ODP/ODS/ODT.
