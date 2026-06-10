# HANDOFF

## Current objective

Prepare the current hardening changes for release as `0.1.3`.

## Completed in this session

- Promoted package metadata from `0.1.2` to `0.1.3` in `pyproject.toml`.
- Moved the current changelog release entry to `0.1.3 — 2026-06-10`.
- Refreshed the local editable install so installed package metadata reports
  `0.1.3`.
- Re-ran the full local test contract and release verification.
- Ran the standalone fresh-install wheel smoke from `CONTRIBUTING.md`.
- Built fresh `0.1.3` sdist and wheel artifacts in a temporary directory.
- Verified both artifacts with `twine check`.
- Installed both the built sdist and wheel into fresh virtualenvs and ran the
  package-owned in-house tournament smoke; both reported version `0.1.3` and
  promoted `inhouse`.

## Current status

The working tree contains the expected release/hardening/docs/tests diff. The
full test suite is green at 646 tests. Fresh `0.1.3` sdist and wheel artifacts
passed `twine check` and install-smoke tests from clean virtualenvs. TestPyPI
and production PyPI publishing have not been run from this environment.

## Next step

Review and commit the uncommitted `0.1.3` release diff, then run the TestPyPI
upload/install verification from `docs/releases/testpypi-execution-checklist.md`
before production publishing.

## Important files

- `pyproject.toml`
- `CHANGELOG.md`
- `src/anydoc2md/format_converters/tournament/orchestrator.py`
- `src/anydoc2md/format_converters/tournament/runner.py`
- `src/anydoc2md/format_converters/tournament/selector.py`
- `tests/test_tournament_orchestrator.py`
- `tests/test_selector.py`
- `README.md`
- `docs/agent-conversion-guide.md`
- `docs/specs/multi-method-converter-tournament.md`
- `docs/progress/20260610.md`

## Notes for next session

- Verified commands:
  - `python -m pip install -e . --no-deps`: installed `any-doc-to-md 0.1.3`.
  - `python - <<'PY' ... metadata('any-doc-to-md')['Version'] ... PY`: printed `0.1.3`.
  - `python -m pytest -q`: 646 passed.
  - `PYTHONPATH=src python -m pytest -q`: 646 passed.
  - `python -m build --sdist --wheel --outdir "$tmpdir/dist"`: built `any_doc_to_md-0.1.3.tar.gz` and `any_doc_to_md-0.1.3-py3-none-any.whl`.
  - `python -m twine check "$tmpdir"/dist/*`: both artifacts passed.
  - Built sdist install smoke: passed with version `0.1.3`, license expression
    `Apache-2.0`, Python 3.11 classifier present, and `winner=inhouse`.
  - Built wheel install smoke: passed with version `0.1.3` and `winner=inhouse`.
  - `python -m pip wheel . -w "$tmpdir/wheelhouse"` plus fresh virtualenv smoke:
    passed with version `0.1.3` and `winner=inhouse`.
  - `git diff --check`: passed.
  - Tracked artifact scan: no tracked `.env`, `.pypirc`, key/cert,
    wheel/tarball/archive, database, model, or pickle/joblib artifacts found.
  - Secret-pattern scan: hits were documented API-key environment-variable
    placeholders and fake `sk-test` values in tests; no real credentials found.
- The release compatibility framing remains: default output may change by
  paragraph whitespace/boundaries; existing CLI/module calls remain compatible;
  `--paragraph-repair off` / `paragraph_repair="off"` preserves raw adapter
  Markdown.
- Local generated release artifacts and smoke virtualenvs are in temporary
  `/tmp` directories; generated repo-local build state is ignored.

## Last updated

2026-06-10 09:28 UTC
