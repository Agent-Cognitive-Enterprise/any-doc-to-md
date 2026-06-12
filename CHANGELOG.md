# Changelog

All notable changes to ADTM will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- The in-house PDF converter now emits PyMuPDF-detected ruled tables as native
  Markdown tables by default. Use `table_extraction: off` in
  `document.override.yaml` to preserve legacy flattened table text for a
  specific document.

## 0.1.3 — 2026-06-10

### Added

- **Deterministic paragraph-continuity repair** for row-sliced Markdown prose.
  Default conversions now run a local, quality-gated repair before
  project-local fix extensions. Accepted repairs preserve raw adapter
  `index.md`, publish through `index_fixed.md`, and write bounded repair
  evidence sidecars in staging.

- **Repair opt-out** via `--paragraph-repair off` in the CLI and
  `paragraph_repair="off"` for `run_full_tournament(...)`. Existing CLI and
  module calls remain compatible.

- **Row-sliced paragraph QA visibility** through the warning-level
  `paragraph_not_row_sliced` check and modest score penalty, so unrepaired
  fragmented prose is less likely to win without becoming a hard gate.

- **Structured QA issue metadata** on built-in warning/failure results:
  optional `violation_type`, `severity`, and `confidence` fields are emitted for
  consumers that need issue classification. Legacy pass-shaped check payloads
  and extension results without explicit metadata remain unchanged.

- `anydoc2md-result.json` now includes top-level `adapter_results` with full
  per-adapter run status, timing, exit code, and error-message evidence.

### Changed

- Fix extensions now build on a trusted paragraph-repair candidate when one is
  present, while keeping the raw adapter output available for inspection.

- Selection, publishing, and post-selection audit consistently evaluate the
  effective candidate Markdown (`index_fixed.md` when present).

- The public benchmark corpus includes a row-sliced text fixture that proves the
  default repair path through the real CLI/in-house/tournament pipeline.

### Fixed

- Stale generated staging artifacts are cleared more aggressively before reruns
  and after failed adapter runs, preventing prior outputs from being selected or
  published accidentally.

- Paragraph-repair and staging cleanup now handle files, directories, symlinks,
  broken symlinks, and concurrent cleanup races safely.

- Tournament wall-clock timeout handling now returns a timeout result without
  waiting for a blocked adapter thread to finish. Python cannot kill a running
  thread, so full late-write isolation still requires a process-level adapter
  boundary.

- Direct selector calls now honor a runner-written `adapter_result.json` sidecar:
  if it records a non-`ok` status, that adapter is disqualified before any
  Markdown is scored, even if a late `index.md` exists on disk.

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
