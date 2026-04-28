# ADTM TestPyPI Execution Checklist

Use this checklist for the first dry run before any production PyPI upload.

This document is intentionally procedural. If any required item fails, stop and
fix that failure before continuing.

## Preconditions

- the private maintainer runbook has concrete primary and backup PyPI owner
  handles
- the private maintainer runbook records the `0.1.0` PyMuPDF acceptance
  decision
- TestPyPI Trusted Publishing is configured for the public repository
- the GitHub `testpypi` environment exists and has the intended reviewers
- the package version in `pyproject.toml` is the version you intend to test
- `CHANGELOG.md` is updated for that version

## Local Verification Before Tagging

From the repository root:

```bash
PYTHONPATH=src python -m pytest -q
```

```bash
tmpdir="$(mktemp -d)"
rm -rf build dist src/*.egg-info
python -m pip install --upgrade build twine
python -m build --sdist --wheel --outdir "$tmpdir/dist"
python -m twine check "$tmpdir"/dist/*
```

Expected result:

- tests pass
- build completes
- `twine check` passes

Stop if:

- tests fail
- build fails
- metadata rendering fails

## Tagging And Upload

Create an annotated tag for the test release candidate:

```bash
git tag -a vVERSION -m "ADTM vVERSION"
git push origin vVERSION
```

Expected result:

- the release workflow starts from the pushed annotated tag
- the TestPyPI publish job requests approval from the `testpypi` environment if
  reviewers are required
- the publish job completes without falling back to manual tokens

Stop if:

- the workflow does not start
- Trusted Publishing is rejected by TestPyPI
- the workflow tries to use an unexpected credential path

## TestPyPI Install Verification

After the upload succeeds, verify the package from TestPyPI in a clean virtual
environment:

```bash
tmpdir="$(mktemp -d)"
python -m venv "$tmpdir/testpypi-venv"
"$tmpdir/testpypi-venv/bin/python" -m pip install --upgrade pip
"$tmpdir/testpypi-venv/bin/python" -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  any-doc-to-md==VERSION
```

Run the import and smoke check:

```bash
"$tmpdir/testpypi-venv/bin/python" - <<'PY'
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-testpypi-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)

assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
print(f"winner={result.winner} output={staging / 'winner' / 'index.md'}")
PY
```

Expected result:

- install succeeds from TestPyPI
- `import anydoc2md` succeeds implicitly through the smoke
- the smoke tournament promotes `inhouse`

Stop if:

- installation fails because dependencies are missing or metadata is broken
- import fails
- the smoke run fails on package-owned fixtures

## Runbook Update

Record these items in the private maintainer runbook:

- TestPyPI version tested
- verification date
- verifier name/handle
- pass or fail result
- any notes about Trusted Publishing, install behavior, or smoke output

## Promotion Rule

Do not create or approve the production PyPI release until:

- the TestPyPI upload succeeded
- the clean-venv install succeeded
- the package-owned smoke run succeeded
- the runbook entry is complete
