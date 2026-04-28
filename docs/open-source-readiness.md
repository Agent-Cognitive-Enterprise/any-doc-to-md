# ADTM Open Source Readiness

This checklist tracks what must be true before publishing ADTM as an open
source project.

## Release Decision

- Release boundary: this `any-doc-to-md` repository
- Public license: Apache-2.0
- Package name: `any-doc-to-md`
- Python package import: `anydoc2md`
- Initial public posture: repo-first CLI and library, installable from a clone
- Default converter set: `inhouse` only
- Optional adapters: `markitdown`, `docling`, `unstructured`, `pandoc`, `marker`
- Benchmark policy: dated, hardware-scoped, cost-aware snapshots only
- PyPI publishing: optional later distribution path, not required to make the
  repository open source

Private downstream integration scripts, private corpora, local benchmark dumps,
API keys, and generated runtime artifacts are not part of the initial ADTM
open-source release unless explicitly extracted later.

## Release Gates

### Scope And Packaging

- [x] Release this standalone `any-doc-to-md` repository.
- [x] Keep ADTM usable as a CLI and library.
- [x] Keep `inhouse` as the only default adapter.
- [x] Verify fresh editable install from a clean checkout.
- [x] Verify fresh wheel install from a local build artifact.
- [x] Add package entry points for the repo-friendly ADTM CLI and helper tools.
- [x] Confirm the public repo already exists and this checkout points at it.

### License And Dependency Hygiene

- [x] Use Apache-2.0 as the public license.
- [x] Keep `LICENSE` at the package root.
- [x] Align `pyproject.toml` package metadata with Apache-2.0.
- [x] Add dependency-license notes for required runtime dependencies.
- [x] Document optional adapter license boundaries:
  `markitdown`, `docling`, `unstructured`, `pandoc`, and `marker`.
- [x] Keep `pymupdf-layout` and PyMuPDF4LLM-style layout stacks out of default
  dependencies unless users explicitly accept their current upstream license,
  model, and dependency terms.
- [ ] Add `NOTICE` only if the final dependency/license audit requires it.

### Secret, Artifact, And Data Hygiene

- [x] Run a secret scan before export or publish.
- [x] Confirm no `.env`, API keys, local tokens, private keys, credentials, or
  service endpoints are included.
- [x] Confirm no local model weights, ONNX exports, downloaded archives, venvs,
  caches, or generated benchmark outputs are included.
- [x] Confirm raw `/tmp` benchmark artifacts stay out of git.
- [x] Confirm benchmark docs use curated summaries, not raw local dumps.
- [x] Replace or remove machine-specific absolute paths from public docs.
- [x] Expand `.gitignore` for local env files, caches, generated ADTM state,
  benchmark outputs, archives, local corpora, and model artifacts.

### Public Documentation

- [x] README explains the core ADTM idea and tournament model.
- [x] README documents the current default adapter policy.
- [x] README includes a dated adapter comparison table.
- [x] Dedicated benchmark snapshot records date, hardware, cost, and caveats.
- [x] Add a public installation section for a clean external user.
- [x] Add a public quickstart using only package-owned test/sample inputs.
- [x] Add a public adapter guide with required tools, optional extras, and known
  limitations.
- [x] Add an LLM judge setup guide with local and cloud-provider cost warnings.
- [x] Add a public learning-loop guide that explains detection, gate/check
  extension, remediation scaffolds, and review boundaries with examples.
- [x] Add troubleshooting notes for PyMuPDF, optional adapters, and missing
  images.
- [x] Add a release-support matrix for Python versions and operating systems.

### Tests And CI

- [x] Package has a broad pytest suite.
- [x] Define the public default CI command.
- [x] Add public CI for tests, CLI smoke, build, and `twine check`.
- [ ] Split fast unit tests from slow or integration adapter tests.
- [x] Ensure default CI has no network dependency.
- [x] Ensure default CI does not spend cloud API credits.
- [x] Add optional CI jobs or documented local commands for external adapters.
- [x] Add a fresh-install smoke test.
- [x] Add a small fixture conversion smoke test that does not rely on
  private corpus paths.

### Security And Contribution Process

- [x] Add `SECURITY.md`.
- [x] Add concrete GitHub private vulnerability reporting path to
  `SECURITY.md`; maintainers must enable it before flipping visibility.
- [x] Add `CONTRIBUTING.md`.
- [x] Add a public issue template for conversion-quality bugs.
- [x] Add a public issue template for adapter installation failures.
- [x] Add a PR checklist covering tests, docs, benchmarks, dependency changes,
  and cost disclosures.
- [x] Add `CODE_OF_CONDUCT.md`.
- [x] Document how users can share failing documents safely without leaking
  sensitive content.

### Release Engineering

- [x] Decide versioning policy after `0.1.0`.
- [x] Add `CHANGELOG.md`.
- [x] Add build verification for wheel install.
- [x] Add build verification for sdist install.
- [x] Keep PyPI publishing flow and credential policy documented for a future
  package upload.
- [x] Include `LICENSE` explicitly in `MANIFEST.in`.
- [x] Decide signed tag or release artifact policy.
- [x] Confirm package metadata, classifiers, readme rendering, and license
  metadata before publish.
- [x] Create a first public release checklist artifact in-repo so it can be
  mirrored into a GitHub issue or milestone at repo split/publish time.

### Benchmark And Cost Policy

- [x] Keep dated benchmark tables in docs.
- [x] Include date, hardware, corpus, mode, and cost context in benchmark docs.
- [x] State that local runs can still cost time/electricity even when API cost
  is `$0`.
- [x] Add a public benchmark reproduction guide that does not depend on private
  downstream paths.
- [x] Add a small public benchmark corpus or fixture set.
- [x] Define how cloud-judge benchmark costs are reported, including date and
  provider/model names.
- [x] Define when benchmark numbers are stale enough to refresh.

## Initial Public Release Blockers

These must be complete before making the repository public:

1. Clean secret scan.
2. Clean fresh install from a checkout.
3. Clean sdist/wheel build and install.
4. Public quickstart that does not require private downstream paths.
5. Default test command documented and passing.
6. License/dependency audit completed, including a decision on PyMuPDF's
   AGPL/commercial required-runtime dependency.
7. `SECURITY.md` and `CONTRIBUTING.md` added.
8. Benchmark docs checked for date, hardware, cost, and corpus caveats.
9. Generated artifacts and benchmark dumps confirmed ignored or absent.
10. CLI quickstart verified from a clean clone or editable install.
11. Release notes and version tag prepared.

PyPI owner handles, TestPyPI, and Trusted Publishing are blockers only for a
package upload. They are not blockers for opening the repository.

## Latest Public-Surface Audit

Audit date: `2026-04-28`

- Full test suite passed: `PYTHONPATH=src python -m pytest -q` ->
  `397 passed`.
- CLI smoke passed with `python -m anydoc2md convert` against
  `examples/quickstart/field-note.txt`.
- Build verification passed: sdist and wheel built cleanly, `twine check`
  passed, wheel installed into a fresh virtualenv, and the installed
  `anydoc2md adapters` console script ran.
- GitHub workflow and Dependabot YAML parsed successfully.
- Secret-like string scan found only documented placeholder environment
  variable examples such as `OPENAI_API_KEY="..."` and fake test keys such as
  `sk-test`; no real credentials were found.
- No tracked `.env`, private keys, certificates, local databases, ONNX exports,
  model weights, downloaded archives, wheels, tarballs, or private corpora were
  found.
- Generated `build/`, `src/any_doc_to_md.egg-info/`, and `__pycache__/`
  directories are ignored local state.
- Source distribution includes `LICENSE`, `SECURITY.md`,
  `.github/workflows/ci.yml`, and `.github/dependabot.yml`.
- Historical private-corpus benchmark references remain only in dated benchmark
  context and are not required for public reproduction.

## Recommended First Implementation Slice

1. Run the final public-surface audit immediately before flipping repository
   visibility.
2. Mirror the repo-owned `0.1.0` checklist into a public GitHub issue or
   milestone when maintainers are ready to track release operations publicly.
