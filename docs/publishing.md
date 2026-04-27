# ADTM Publishing Policy

Review date: `2026-04-24`

This document defines the initial publishing policy for `any-doc-to-md`.
It covers release authority, PyPI credentials, trusted publishing, fallback
tokens, and the minimum release sequence.

## Decision

- Publish package name: `any-doc-to-md`
- Import package: `anydoc2md`
- Initial release line: `0.x`
- Default publishing path: PyPI Trusted Publishing from GitHub Actions OIDC
- Production environment name: `pypi`
- Test environment name: `testpypi`
- Release workflow filename: `.github/workflows/release.yml`
- Long-lived PyPI API tokens: emergency/manual fallback only
- Release tag policy: protected annotated tags matching `v*`
- Cryptographic signing policy for `0.1.x`: not required for the first public
  release; authenticity is enforced through protected tags, reviewed GitHub
  releases, and PyPI Trusted Publishing OIDC
- Required human control: protected GitHub environment with manual approval for
  production PyPI uploads

## Owners

Before the first public upload, assign:

- one primary PyPI project owner
- one backup PyPI project owner
- at least one GitHub repository administrator who is not the only PyPI owner

All PyPI owner and maintainer accounts must have two-factor authentication
enabled. Do not rely on a single human account for package recovery.

Record the concrete owner handles in the private release checklist or the
public repository's maintainer runbook. Do not put personal recovery codes,
passwords, API tokens, or private email-only recovery details in this repo.

## Trusted Publishing Setup

Use PyPI Trusted Publishing because it avoids storing a long-lived upload token
in GitHub secrets. PyPI issues a short-lived token during the authorized OIDC
flow, and the workflow uses that token for the upload.

For PyPI production:

1. Create or claim the `any-doc-to-md` project on PyPI.
2. Open the project's publishing settings.
3. Add a GitHub Actions trusted publisher.
4. Configure the public repository owner, repository name, and workflow file
   as `.github/workflows/release.yml`.
5. Set the GitHub environment to `pypi`.
6. Configure the GitHub `pypi` environment with required reviewers.
7. Protect release tags such as `v*` so only maintainers can create or mutate
   release tags.

For TestPyPI, repeat the same pattern with a `testpypi` environment before the
first production release.

Reference docs:

- PyPI Trusted Publishers:
  <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>
- PyPI Trusted Publishing security model:
  <https://docs.pypi.org/trusted-publishers/security-model/>
- GitHub OIDC for PyPI:
  <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi>
- PyPI 2FA enforcement:
  <https://blog.pypi.org/posts/2024-01-01-2fa-enforced/>

## Release Workflow Shape

Keep publishing in a small, isolated workflow. The publishing job should have
only the permissions needed to read the built artifacts and request an OIDC
token.

Recommended shape:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install --upgrade build twine
      - run: rm -rf build dist src/*.egg-info
      - run: python -m build --sdist --wheel --outdir dist
      - run: python -m twine check dist/*
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/*

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1
```

If the public repo uses a monorepo layout, set the build job working directory
to `packages/any-doc-to-md` or split ADTM into its own repository before
enabling production publishing.

## Tag And Release Artifact Policy

For the initial `0.1.x` public line:

- create annotated git tags only, using the form `vMAJOR.MINOR.PATCH`
- protect `v*` tags so only maintainers can create them
- cut GitHub release notes from `CHANGELOG.md`
- publish only artifacts built by CI from the tagged commit
- do not upload maintainer-built local wheels or sdists to PyPI
- do not require GPG or Sigstore signing for `0.1.x`

Rationale:

- PyPI Trusted Publishing already binds the upload to the GitHub Actions OIDC
  identity for the tagged workflow run
- protected tags and required environment approval are simpler to operate than
  ad hoc maintainer signing for the first release
- this keeps the first public release process auditable without inventing a
  brittle signature workflow before the package has even shipped once

Revisit artifact signing after the first public release if maintainers want
Sigstore-based provenance or signed tags as an additional control.

## Release Sequence

Before publishing:

1. Confirm the version in `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Run `python -m pytest -q` from a clean editable install.
4. Run the release verification command in `CONTRIBUTING.md`.
5. Confirm `twine check` passes for both sdist and wheel.
6. Confirm the source distribution contains public docs, examples, issue
   templates, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `LICENSE`.
7. Run the secret/artifact audit from `docs/open-source-readiness.md`.
8. Publish to TestPyPI and install from TestPyPI in a clean virtualenv.
9. Create the production tag only after TestPyPI verification passes.
10. Approve the protected `pypi` environment deployment.
11. Verify the PyPI project page, metadata, and install command after upload.
12. Create GitHub release notes from `CHANGELOG.md`.

## TestPyPI Smoke

After a TestPyPI upload, verify the package in a fresh virtualenv:

```bash
tmpdir="$(mktemp -d)"
python -m venv "$tmpdir/testpypi-venv"
"$tmpdir/testpypi-venv/bin/python" -m pip install --upgrade pip
"$tmpdir/testpypi-venv/bin/python" -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  any-doc-to-md==VERSION
"$tmpdir/testpypi-venv/bin/python" - <<'PY'
import anydoc2md
print(anydoc2md.__name__)
PY
```

Use `--extra-index-url` because TestPyPI usually does not mirror every runtime
dependency.

## Emergency Token Fallback

Use a long-lived API token only when Trusted Publishing is unavailable and the
release cannot wait.

Fallback rules:

- Use a project-scoped token, never an account-wide token.
- Store it only in an approved secret manager or a protected GitHub environment
  secret.
- Rotate it immediately after use.
- Remove it from GitHub once Trusted Publishing is restored.
- Record the reason for token use in the release notes or private release log.

Do not commit `.pypirc`, token values, recovery codes, or upload credentials.

## Yank And Recovery Policy

If a broken release is uploaded:

- prefer a new patch release when the package can be superseded safely
- yank the release on PyPI when the artifact is bad but should remain visible
  for users with pinned installs
- contact PyPI support only for cases that require administrative intervention

Never overwrite a published version. PyPI release files are immutable for
normal release management purposes.
