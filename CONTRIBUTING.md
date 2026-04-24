# Contributing To ADTM

ADTM treats document conversion as an evaluation problem. Contributions should
preserve that discipline: converters may be imperfect, but failures must be
observable, testable, and documented.

## Development Setup

From the package root:

```bash
python -m pip install -e ".[test]"
```

Default test command:

```bash
python -m pytest -q
```

The default test suite must not require network access, API keys, cloud LLM
credits, private corpora, local model weights, or optional converter binaries.

## Fresh Install Smoke

Use this smoke after package metadata, dependency, or release changes:

```bash
tmpdir="$(mktemp -d)"
python -m pip wheel . -w "$tmpdir/wheelhouse"
python -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install "$tmpdir"/wheelhouse/*.whl
"$tmpdir/venv/bin/python" - <<'PY'
from pathlib import Path
from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-open-source-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)
assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
print(f"winner={result.winner} output={staging / 'winner' / 'index.md'}")
PY
```

The smoke uses only the committed quickstart fixture and the default `inhouse`
adapter. It must not call an LLM judge or external converter.

## Release Verification

Use this after package metadata, versioning, or release-doc changes.
Supported Python and operating-system claims are tracked in
[`docs/release-support-matrix.md`](docs/release-support-matrix.md).

```bash
tmpdir="$(mktemp -d)"
rm -rf build dist src/*.egg-info
python -m pip install --upgrade build twine
python -m build --sdist --wheel --outdir "$tmpdir/dist"
python -m twine check "$tmpdir"/dist/*
python -m venv "$tmpdir/sdist-venv"
"$tmpdir/sdist-venv/bin/python" -m pip install "$tmpdir"/dist/*.tar.gz
"$tmpdir/sdist-venv/bin/python" - <<'PY'
from importlib.metadata import metadata
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-open-source-sdist-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)

meta = metadata("any-doc-to-md")
classifiers = meta.get_all("Classifier") or []
assert meta["License-Expression"] == "Apache-2.0"
assert "Programming Language :: Python :: 3.11" in classifiers
assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
print(f"license_expression={meta['License-Expression']}")
print(f"classifiers={classifiers}")
print(f"winner={result.winner} output={staging / 'winner' / 'index.md'}")
PY
```

This verifies README rendering via `twine check`, confirms package classifiers
are present in installed metadata, and smoke-tests an install from the built
sdist. Keep the generated temp directories and `/tmp/adtm-open-source-sdist-smoke`
out of git.

Publishing policy, TestPyPI flow, PyPI owner requirements, and emergency token
fallback rules are documented in [`docs/publishing.md`](docs/publishing.md).

## Optional Adapter Testing

Optional adapters are first-class but not part of the default test contract.
Run them explicitly when changing adapter code or dependency documentation.

Use the maintained local commands in
[`docs/adapter-integration-tests.md`](docs/adapter-integration-tests.md).
Use [`docs/adapter-guide.md`](docs/adapter-guide.md) for adapter selection,
image behavior, install boundaries, and known limitations.
Review dependency and license boundaries in
[`docs/dependency-license-notes.md`](docs/dependency-license-notes.md) before
changing adapter dependencies.

Expected boundaries:

- `inhouse`: default adapter; must work without external converter binaries
- `markitdown`: optional subprocess-backed adapter
- `docling`: optional subprocess-backed adapter
- `unstructured`: optional Python ecosystem adapter with extra system
  dependencies for some formats
- `pandoc`: optional subprocess-backed adapter; useful for text-centric formats
- `marker`: optional subprocess-backed PDF adapter

Do not add optional converter packages, OCR stacks, model weights, or
commercially restricted dependencies to the default install without a dated
benchmark and licensing rationale.

## Pull Request Checklist

Before opening a PR, confirm:

- tests were added or updated for behavior changes
- `python -m pytest -q` passes from the package root
- docs were updated for behavior, setup, adapter, benchmark, or cost changes
- new files are intentionally committed source/docs/fixtures, or ignored if
  generated/local
- no secrets, private corpora, generated benchmark dumps, model weights,
  virtualenvs, caches, or downloaded archives were added
- benchmark numbers include date, hardware, corpus, mode, and cost context
- public benchmark reproduction changes follow
  [`docs/benchmark-reproduction.md`](docs/benchmark-reproduction.md)
- cloud/API costs are disclosed with date and provider/model names
- LLM judge setup or benchmark changes follow
  [`docs/llm-judge-setup.md`](docs/llm-judge-setup.md)
- troubleshooting guidance was updated when setup or failure modes changed
- dependency changes include license and install-footprint notes

## Reporting Conversion Bugs

Useful conversion bug reports include:

- source format and size
- adapter set used
- audit mode
- expected Markdown behavior
- actual output excerpt or QA failure
- whether images, tables, OCR, equations, or multi-column layout are involved

Do not upload sensitive documents publicly. Prefer a minimal synthetic
reproduction that preserves the structure of the failure.

## Coding Guidelines

- Keep changes scoped and small.
- Prefer deterministic checks before LLM-based judgment.
- Keep generated artifacts out of git.
- Preserve the stable staging shape: `index.md`, `images/`, and
  `adapter_result.json`.
- Keep default paths fast, local, and cost-free.
