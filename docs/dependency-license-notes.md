# ADTM Dependency And License Notes

Review date: 2026-04-23.

These notes are not legal advice. They are a maintainer-facing checklist for
keeping ADTM's default install small, auditable, and honest before public
release. Re-check exact versions and transitive dependencies before publishing
or redistributing a release artifact.

## Release Policy

- ADTM package code is licensed as Apache-2.0.
- The default install must not silently install optional converter stacks, model
  weights, OCR engines, or commercially restricted layout packages.
- Required dependencies must be reviewed before public release because they are
  installed for every user.
- Optional adapters stay default-off. Users opt in to their upstream packages,
  tools, model terms, and system dependencies.
- Benchmark dumps, source corpora, downloaded archives, virtualenvs, model
  weights, and API keys are not dependencies and must not be committed.

## Required Runtime Dependencies

These dependencies are declared in `pyproject.toml` and are installed by the
base package.

| Dependency | Current ADTM use | License note checked on 2026-04-23 | Release action |
|---|---|---|---|
| `PyMuPDF` | PDF text, image, page, and rendering support used by the in-house converter and PDF audit flow | PyPI lists PyMuPDF as dual licensed under GNU AGPL-3.0 or Artifex Commercial License. | Treat as the main release-audit item. Downstream users must be told that PDF support depends on PyMuPDF's AGPL/commercial terms. |
| `PyYAML` | YAML config and override parsing | PyPI lists MIT. | Keep required unless replaced by standard-library-only config. |
| `beautifulsoup4` | HTML parsing and cleanup | PyPI lists MIT. | Keep required for HTML support. |
| `requests` | HTTP client support in shared helpers | PyPI lists Apache-2.0. | Keep required only if runtime code still needs it; otherwise consider moving to an optional extra later. |

Primary references:

- PyMuPDF PyPI license metadata: <https://pypi.org/project/PyMuPDF/>
- PyYAML PyPI metadata: <https://pypi.org/project/PyYAML/>
- Beautiful Soup PyPI metadata: <https://pypi.org/project/beautifulsoup4/>
- Requests PyPI metadata: <https://pypi.org/project/requests/>

## Optional Adapter Boundaries

These adapters are implemented and supported as first-class optional adapters,
but they are not part of ADTM's default adapter set or base install.

| Adapter | Upstream package or tool | License note checked on 2026-04-23 | Boundary |
|---|---|---|---|
| `markitdown` | Microsoft MarkItDown | GitHub lists MIT. MarkItDown also has optional OCR, Azure Document Intelligence, and LLM-assisted paths that may add service costs or extra terms when enabled upstream. | Optional CLI boundary. ADTM does not enable cloud services or LLM image descriptions for MarkItDown. |
| `docling` | Docling CLI | GitHub and PyPI list MIT for the codebase; model usage can carry separate model licenses. | Optional CLI boundary. Users install Docling and accept its package and model terms. |
| `unstructured` | `unstructured` Python package | GitHub and PyPI list Apache-2.0. The broad `unstructured[all-docs]` install has a large transitive footprint and can require system tools such as `libmagic`, `poppler`, `tesseract`, and `libreoffice`. | Optional Python/subprocess boundary. Keep out of the default install. |
| `pandoc` | Pandoc CLI | Pandoc source states GPL-2.0-or-later for the main code, with noted exceptions. | Optional external executable boundary. Do not vendor or bundle without legal review. |
| `marker` | Marker / `marker-pdf` CLI | GitHub lists GPL-3.0 code. Its README states model weights use a modified AI Pubs OpenRAIL-M license with commercial restrictions. | Optional external executable/model boundary. Do not vendor code, model weights, or default-enable without legal and product review. |

Primary references:

- MarkItDown repository: <https://github.com/microsoft/markitdown>
- Docling repository: <https://github.com/docling-project/docling>
- Docling PyPI metadata: <https://pypi.org/project/docling/>
- Unstructured repository: <https://github.com/Unstructured-IO/unstructured>
- Unstructured PyPI metadata: <https://pypi.org/project/unstructured/>
- Pandoc copyright and license file: <https://github.com/jgm/pandoc/blob/main/COPYRIGHT>
- Marker repository: <https://github.com/datalab-to/marker>

## Explicit Non-Default Layout Packages

`pymupdf-layout` and PyMuPDF4LLM-style layout stacks are not ADTM default
dependencies. A local 2026-04-23 test removed the PyMuPDF table-layout warning
but did not improve the default in-house corpus result enough to justify the
license and performance footprint.

Current upstream notes to re-check before any future use:

- PyMuPDF4LLM PyPI lists GNU AGPL-3.0 or Artifex Commercial License.
- The PyMuPDF4LLM changelog says PyMuPDF-Layout is not open-source, has its own
  license, and brings additional large dependencies.

Policy: keep these packages out of `pyproject.toml` unless the user explicitly
opts in and the release notes document the exact version, license, benchmark
impact, and commercial-use constraints.

Primary references:

- PyMuPDF4LLM PyPI metadata: <https://pypi.org/project/pymupdf4llm/>
- PyMuPDF4LLM changelog: <https://github.com/pymupdf/pymupdf4llm/blob/main/CHANGES.md>

## Before Public Release

- Run a license scanner against the locked release environment.
- Review direct and transitive dependencies for the exact versions to publish.
- Decide whether PyMuPDF's AGPL/commercial dependency is acceptable for the base
  package or whether PDF support must become an extra.
- Add `NOTICE` only if the final audit requires it.
- Keep every optional adapter documented with install, test, license, and cost
  notes.
