# HANDOFF

## Current objective

Prepare the merged paragraph-continuity-repair work for release as `0.1.2`.

## Completed in this session

- Bumped the package version in `pyproject.toml` from `0.1.1` to `0.1.2`.
- Added a `CHANGELOG.md` entry for `0.1.2 — 2026-06-10`.
- The changelog calls out the intentional default-output behavior change:
  deterministic paragraph repair can alter paragraph whitespace/boundaries when
  accepted, while existing CLI/module calls remain compatible and
  `--paragraph-repair off` / `paragraph_repair="off"` preserves raw adapter
  Markdown.
- Refreshed the local editable install with `python -m pip install -e . --no-deps`
  so installed package metadata reports `0.1.2`.
- Installed the release tooling (`build`, `twine`) and ran the local release
  verification from `CONTRIBUTING.md`.
- Built both release artifacts in a temporary directory:
  `any_doc_to_md-0.1.2.tar.gz` and `any_doc_to_md-0.1.2-py3-none-any.whl`.
- Confirmed `twine check` passes for both the sdist and wheel.
- Verified the sdist contains the required public docs/examples/support files,
  including `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  `README.md`, `.github/ISSUE_TEMPLATE/`, `docs/`, and `examples/`.
- Installed both the built sdist and wheel into fresh virtualenvs and ran the
  package-owned in-house tournament smoke; both reported version `0.1.2` and
  promoted `inhouse`.
- Ran the local tracked-file artifact/secret scan. It found no tracked archives,
  private-key files, databases, model artifacts, or real credentials; hits were
  documented API-key environment-variable placeholders and fake `sk-test` values
  in tests.

## Current status

The working tree has release-prep edits only: `pyproject.toml`, `CHANGELOG.md`,
and this `HANDOFF.md`/progress record. Source behavior is unchanged from the
merged branch. The package metadata now reports version `0.1.2`; local release
verification, artifact checks, install smokes, and the full test suite are
green. TestPyPI/production publishing has not been run from this environment.

## Next step

Review the `0.1.2` changelog wording, then commit the release-prep changes.
After committing, follow `docs/releases/testpypi-execution-checklist.md` for the
TestPyPI upload/install verification before approving production PyPI.

## Important files

- `pyproject.toml`
- `CHANGELOG.md`
- `docs/publishing.md`
- `docs/releases/testpypi-execution-checklist.md`
- `docs/progress/20260610.md`

## Notes for next session

- Verified commands:
  - `python -m pip install -e . --no-deps`: installed `any-doc-to-md 0.1.2`.
  - `python -c "from importlib.metadata import metadata; print(metadata('any-doc-to-md')['Version'])"`: printed `0.1.2`.
  - `python -m pytest -q`: 642 passed.
  - `PYTHONPATH=src python -m pytest -q`: 642 passed.
  - `python -m build --sdist --wheel --outdir "$tmpdir/dist"`: built sdist and wheel.
  - `python -m twine check "$tmpdir"/dist/*`: passed for both artifacts.
  - Built sdist install smoke: passed with version `0.1.2`, license expression
    `Apache-2.0`, Python 3.11 classifier present, and `winner=inhouse`.
  - Built wheel install smoke: passed with version `0.1.2` and `winner=inhouse`.
  - `git diff --check`: clean.
- Remaining historical `0.1.1` references are changelog history only.
- Local generated release/build state exists only in ignored paths (`build/`,
  `src/any_doc_to_md.egg-info/`, test caches/venvs) and temporary `/tmp`
  directories; nothing generated is staged or untracked.
- The release note should retain this compatibility framing: default output may
  change by paragraph whitespace/boundaries; existing CLI/module calls remain
  compatible; `--paragraph-repair off` / `paragraph_repair="off"` preserves raw
  adapter Markdown.

## Last updated

2026-06-10 07:10 UTC
