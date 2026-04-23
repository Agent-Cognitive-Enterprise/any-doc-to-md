# Security Policy

## Supported Versions

ADTM is preparing its first public open-source release. Until a stable release
line exists, security fixes target the current `main` branch and the latest
published package version, if any.

## Reporting A Vulnerability

Report suspected security issues privately. Do not open a public issue for:

- secrets or credentials accidentally exposed in examples, tests, docs, or
  release artifacts
- path traversal, arbitrary file read/write, unsafe archive extraction, or
  unsafe symlink handling
- prompt-injection paths that can exfiltrate private source content, API keys,
  local file paths, or judge credentials
- unsafe handling of untrusted documents, images, PDFs, archives, or converter
  subprocess output
- dependency confusion, supply-chain, or package publishing issues

For the initial public release, use the repository owner's private security
advisory workflow if available. If the project is mirrored or exported before
GitHub Security Advisories are enabled, contact the maintainers through the
private channel listed on the public repository.

Include:

- affected version or commit
- operating system and Python version
- minimal reproduction steps
- whether the issue requires optional adapters or LLM judge configuration
- whether a sample document is sensitive

Do not attach private, regulated, customer, or personally identifiable
documents to a public issue. If a document is needed to reproduce the issue,
first reduce it to a minimal synthetic fixture or ask maintainers for a private
transfer path.

## Security Scope

In scope for ADTM:

- package code under `src/anydoc2md`
- package-owned tests, fixtures, and docs
- package build and release metadata
- default in-house conversion path
- optional adapter invocation boundaries
- LLM judge prompt construction and result parsing

Out of scope for the initial ADTM package release:

- PRAI host application authentication and deployment
- private PRAI corpora and local benchmark dumps
- third-party converter internals
- local model weights, downloaded archives, and external services

Third-party converter vulnerabilities should also be reported upstream to the
affected project.

## Handling Sensitive Documents

ADTM processes user-provided documents. Treat all source files, extracted text,
images, staging outputs, QA reports, and LLM judge prompts as potentially
sensitive.

Maintainers should avoid requesting real user documents unless a synthetic
reproduction is not possible. When a real document is unavoidable, agree on
retention, redaction, and deletion expectations before transfer.
