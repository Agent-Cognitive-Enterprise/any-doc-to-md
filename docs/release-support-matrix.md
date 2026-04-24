# ADTM Release Support Matrix

Review date: 2026-04-24.

This matrix describes the support posture for the initial ADTM public release.
It separates package metadata from verified test coverage so the project does
not overstate what has been exercised.

## Package Metadata

`pyproject.toml` currently declares:

- `requires-python = ">=3.11"`
- classifier: `Programming Language :: Python :: 3.11`
- classifier: `Operating System :: OS Independent`

Interpretation:

- Python 3.11 is the public release target.
- The code is intended to be portable across operating systems, but optional
  adapters depend on external tools that are not equally available everywhere.
- Do not add a Python version classifier until the default test suite and
  release verification pass on that version.

## Verified Environments

| Environment | Status | Evidence | Notes |
|---|---|---|---|
| Linux x86_64, Ubuntu kernel `6.8.0-110-generic`, Python `3.13.13` | Verified development environment | Full package test suite passed: `377 passed, 2 warnings` on 2026-04-24; sdist/wheel build and `twine check` passed | Current workspace environment. Warnings were existing Torch/CUDA warnings from optional `unstructured` tests. |
| Python 3.11 on Linux | Release target, needs CI verification | Metadata declares Python 3.11 classifier and `requires-python >=3.11` | Add CI coverage before publishing. |
| Python 3.12 on Linux | Intended compatible, unverified | No current committed verification record | Add CI coverage before adding classifier. |
| Python 3.13 on Linux | Development verified, not yet advertised in classifiers | Current workspace test/build verification | Add classifier only after deciding the public support policy. |
| macOS, Python 3.11+ | Intended compatible, unverified | No current committed verification record | Default `inhouse` path should be portable if dependencies install; optional CLI/system tools need separate checks. |
| Windows, Python 3.11+ | Intended compatible, unverified | No current committed verification record | Shell snippets in docs are POSIX-oriented; Windows support needs explicit command and path verification. |

## Adapter Support Boundaries

| Adapter | Default support status | OS sensitivity | Support note |
|---|---|---|---|
| `inhouse` | Default supported adapter | Python dependency installation, especially PyMuPDF wheels | Must pass default CI and release smoke before publish. |
| `markitdown` | First-class optional | Python package and CLI availability | Users opt in to upstream package behavior and optional OCR/cloud features. |
| `docling` | First-class optional | Python package, CLI, model assets, and native dependencies | Users opt in to package/model footprint. |
| `unstructured` | First-class optional | Large Python extras plus system tools such as `libmagic`, `poppler`, `tesseract`, and `libreoffice` | Keep out of default CI except explicit optional adapter jobs. |
| `pandoc` | First-class optional | External `pandoc` executable and PATH behavior | Treat as an external tool boundary. |
| `marker` | First-class optional | Python package, `marker_single` CLI, model assets, acceleration, and license/model terms | Treat as explicit PDF/layout experiment boundary. |

## Minimum Release Verification

Before publishing an ADTM release, run these checks on each advertised Python
version and operating system:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

Run the release artifact check:

```bash
tmpdir="$(mktemp -d)"
rm -rf build dist src/*.egg-info
python -m pip install --upgrade build twine
python -m build --sdist --wheel --outdir "$tmpdir/dist"
python -m twine check "$tmpdir"/dist/*
python -m venv "$tmpdir/sdist-venv"
"$tmpdir/sdist-venv/bin/python" -m pip install "$tmpdir"/dist/*.tar.gz
```

Run a package-only smoke from the installed sdist:

```bash
"$tmpdir/sdist-venv/bin/python" - <<'PY'
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-release-support-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)
assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
print(f"winner={result.winner} output={staging / 'winner' / 'index.md'}")
PY
```

The smoke uses the default adapter, no cloud judge, no optional converter CLI,
and no private corpus.

## CI Recommendation

Initial public CI should include:

- Linux Python 3.11 as the release gate.
- Linux Python 3.12 and 3.13 as compatibility checks before adding classifiers.
- A build job that runs sdist/wheel build plus `twine check`.
- A no-network default test job.
- Separate optional adapter jobs that are explicitly allowed to install
  external packages or system tools.

Do not make optional adapter jobs required for the default package release until
their install footprints and license boundaries are reviewed.

## Updating This Matrix

Update this file when:

- `requires-python` changes.
- Python classifiers change.
- a new OS/Python combination becomes part of release CI.
- an optional adapter becomes part of a supported CI job.
- a dependency changes the supported Python or OS range.

Keep the matrix dated. Support claims should follow verification, not intent.
