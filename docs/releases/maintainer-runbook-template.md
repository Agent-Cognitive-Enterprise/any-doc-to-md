# ADTM Maintainer Runbook Template

Purpose: provide a safe place for maintainers to record release ownership and
approval facts without storing secrets in git.

Do not commit filled-in recovery codes, passwords, API tokens, private email
addresses, or any other secret material. If maintainers duplicate this template
into a private runbook, the private copy should live in an approved secret or
operations system rather than this repository.

## Release Ownership

- Primary PyPI owner handle: `TODO`
- Backup PyPI owner handle: `TODO`
- Additional GitHub repository admin handle(s): `TODO`
- All listed accounts have 2FA enabled: `TODO yes/no`

## Trusted Publishing

- TestPyPI trusted publisher configured: `TODO yes/no`
- PyPI trusted publisher configured: `TODO yes/no`
- GitHub `testpypi` environment reviewers: `TODO`
- GitHub `pypi` environment reviewers: `TODO`

## 0.1.0 PyMuPDF Signoff

- Decision maker: `TODO`
- Decision date: `TODO YYYY-MM-DD`
- Accepted posture:
  `Keep PyMuPDF in the base package for 0.1.0 with explicit AGPL/commercial disclosure.`
- Alternative if rejected:
  `Block release until PDF support moves behind an explicit extra or distribution boundary.`
- Decision outcome: `TODO accepted/rejected`
- Notes: `TODO`

## Release Tag Policy

- Protected annotated tag pattern: `v*`
- Artifact source: `CI-built artifacts only`
- Mandatory signing for `0.1.x`: `No`

## TestPyPI Verification

- TestPyPI version tested: `TODO`
- TestPyPI verification date: `TODO YYYY-MM-DD`
- Clean install verifier: `TODO`
- Result: `TODO pass/fail`
- Notes: `TODO`

## Production Release

- Release tag: `TODO`
- Production approver: `TODO`
- Release date: `TODO YYYY-MM-DD`
- GitHub release URL: `TODO`
- PyPI project URL: `TODO`
- Post-release smoke result: `TODO pass/fail`
