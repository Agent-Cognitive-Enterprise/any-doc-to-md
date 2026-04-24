# ADTM Open Source Readiness

This checklist tracks what must be true before publishing ADTM as an open
source project.

## Release Decision

- Release boundary: `packages/any-doc-to-md`
- Public license: Apache-2.0
- Package name: `any-doc-to-md`
- Python package import: `anydoc2md`
- Initial public posture: library-first package with host-provided CLIs
- Default converter set: `inhouse` only
- Optional adapters: `markitdown`, `docling`, `unstructured`, `pandoc`, `marker`
- Benchmark policy: dated, hardware-scoped, cost-aware snapshots only

PRAI integration scripts, private corpora, local benchmark dumps, API keys,
and generated runtime artifacts are not part of the initial ADTM open-source
release unless explicitly extracted later.

## Release Gates

### Scope And Packaging

- [x] Release `packages/any-doc-to-md` first, not the whole PRAI monorepo.
- [x] Keep ADTM usable as a library with host-provided CLIs.
- [x] Keep `inhouse` as the only default adapter.
- [x] Verify fresh editable install from a clean checkout.
- [x] Verify fresh wheel install from a local build artifact.
- [ ] Add or confirm package entry points if a standalone ADTM CLI becomes part
  of the release.
- [ ] Decide whether the public repo is a split repo or a filtered export from
  the monorepo.

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

- [ ] Run a secret scan before export or publish.
- [ ] Confirm no `.env`, API keys, local tokens, private keys, credentials, or
  service endpoints are included.
- [ ] Confirm no local model weights, ONNX exports, downloaded archives, venvs,
  caches, or generated benchmark outputs are included.
- [ ] Confirm raw `/tmp` benchmark artifacts stay out of git.
- [ ] Confirm benchmark docs use curated summaries, not raw local dumps.
- [ ] Replace or remove machine-specific absolute paths from public docs.

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
- [x] Add troubleshooting notes for PyMuPDF, optional adapters, and missing
  images.
- [x] Add a release-support matrix for Python versions and operating systems.

### Tests And CI

- [x] Package has a broad pytest suite.
- [x] Define the public default CI command.
- [ ] Split fast unit tests from slow or integration adapter tests.
- [x] Ensure default CI has no network dependency.
- [x] Ensure default CI does not spend cloud API credits.
- [x] Add optional CI jobs or documented local commands for external adapters.
- [x] Add a fresh-install smoke test.
- [x] Add a small fixture conversion smoke test that does not rely on PRAI
  private corpus paths.

### Security And Contribution Process

- [x] Add `SECURITY.md`.
- [x] Add `CONTRIBUTING.md`.
- [x] Add a public issue template for conversion-quality bugs.
- [x] Add a public issue template for adapter installation failures.
- [x] Add a PR checklist covering tests, docs, benchmarks, dependency changes,
  and cost disclosures.
- [ ] Decide whether to add `CODE_OF_CONDUCT.md`.
- [x] Document how users can share failing documents safely without leaking
  sensitive content.

### Release Engineering

- [x] Decide versioning policy after `0.1.0`.
- [x] Add `CHANGELOG.md`.
- [x] Add build verification for wheel install.
- [x] Add build verification for sdist install.
- [ ] Decide PyPI publishing flow and package owner credentials.
- [ ] Decide signed tag or release artifact policy.
- [x] Confirm package metadata, classifiers, readme rendering, and license
  metadata before publish.
- [ ] Create a first public release checklist issue or milestone.

### Benchmark And Cost Policy

- [x] Keep dated benchmark tables in docs.
- [x] Include date, hardware, corpus, mode, and cost context in benchmark docs.
- [x] State that local runs can still cost time/electricity even when API cost
  is `$0`.
- [x] Add a public benchmark reproduction guide that does not depend on private
  PRAI paths.
- [ ] Add a small public benchmark corpus or fixture set.
- [x] Define how cloud-judge benchmark costs are reported, including date and
  provider/model names.
- [x] Define when benchmark numbers are stale enough to refresh.

## Initial Public Release Blockers

These must be complete before publishing outside the monorepo:

1. Clean secret scan.
2. Clean fresh install from a checkout.
3. Clean sdist/wheel build and install.
4. Public quickstart that does not require PRAI-private paths.
5. Default test command documented and passing.
6. License/dependency audit completed, including a decision on PyMuPDF's
   AGPL/commercial required-runtime dependency.
7. `SECURITY.md` and `CONTRIBUTING.md` added.
8. Benchmark docs checked for date, hardware, cost, and corpus caveats.
9. Generated artifacts and benchmark dumps confirmed ignored or absent.
10. Release notes and version tag prepared.

## Recommended First Implementation Slice

1. Add a small public benchmark corpus or fixture set if the existing
   quickstart/probe fixtures are not enough for release-facing examples.
2. Run a final secret/artifact audit before export.
3. Decide PyPI publishing flow and package owner credentials.
4. Create a first public release checklist issue or milestone.
5. Decide whether to add `CODE_OF_CONDUCT.md`.
