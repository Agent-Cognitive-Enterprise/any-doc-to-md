# AGENTS.md

This file defines repository-wide instructions for AI coding assistants working on ADTM.

ADTM is a live, public, open-source package. Treat every change as something an external user may install, script against, benchmark, or debug tomorrow. Backward compatibility is not decorative bunting; it is part of the product contract.

If a deeper or path-specific `AGENTS.md` is added later, the more specific file takes precedence for files in that subtree. Otherwise, this root file is the default house law.

---

## 1. Project identity

`anydoc2md` is a CLI-first document-to-Markdown conversion package.

The project treats conversion as an evaluation problem:

- run one or more converter adapters,
- normalize and score their outputs,
- select the best candidate,
- optionally audit with a bounded LLM judge,
- preserve evidence, findings, and remediation scaffolds.

Important existing contracts:

- source code lives under `src/anydoc2md/`,
- the canonical design spec lives at `docs/specs/multi-method-converter-tournament.md`,
- default install and default tests must remain fast, local, deterministic, and cost-free,
- the default runtime adapter set is intentionally conservative,
- optional converter stacks stay optional unless a deliberate release decision says otherwise,
- the stable published output shape is `index.md`, optional `images/`, and `anydoc2md-result.json`,
- tournament staging uses per-adapter directories and a promoted `winner/` directory,
- `index_fixed.md`, when present, is the score-guarded improved Markdown used by selection and publication.

---

## 2. Read before writing

Before making substantive changes:

1. Read this `AGENTS.md`.
2. Read `README.md`.
3. Read the relevant sections of `docs/specs/multi-method-converter-tournament.md`.
4. Read `CONTRIBUTING.md` for test, release, adapter, and contribution boundaries.
5. Inspect the current code and tests around the exact area being changed.
6. Identify acceptance criteria, affected files, compatibility risks, and required verification.
7. Make the smallest coherent plan before editing.

Do not make blind edits. Familiarity is not compliance.

---

## 3. Backward compatibility is mandatory

This repository is public and live. Preserve existing behavior unless the task explicitly authorizes a breaking change.

### 3.1 Public surfaces

Do not break or silently change these without explicit approval and release documentation:

- package name: `any-doc-to-md`,
- import package: `anydoc2md`,
- console scripts such as `anydoc2md`, `anydoc2md-find-judge`, and `anydoc2md-benchmark-matrix`,
- existing CLI commands, options, defaults, exit-code expectations, and output files,
- `run_full_tournament(...)` call compatibility,
- `TournamentResult.to_dict()` consumers,
- `SelectionResult.to_dict()` and scorecard shape,
- adapter result staging expectations,
- project-local `.any-doc-to-md/` extension behavior,
- the default `python -m pytest -q` contract.

Adding fields to JSON may be acceptable only when additive, documented, tested, and unlikely to break strict downstream consumers. Prefer separate sidecar reports for experimental evidence until the contract deserves promotion.

### 3.2 Default behavior

Default paths must remain:

- local,
- deterministic,
- no network,
- no API keys,
- no cloud LLM calls,
- no private corpora,
- no optional converter binaries required,
- no heavyweight model downloads,
- no surprise dependency footprint.

`audit_mode=light` must remain usable without a judge. Optional adapters must not become mandatory by accident.

### 3.3 Output compatibility

Preserve the existing output and staging shape:

```text
output_dir/
  index.md
  images/                 # when extractable images exist
  anydoc2md-result.json
  .any-doc-to-md/staging/ # unless --staging-dir is supplied
```

Preserve adapter staging expectations:

```text
staging_root/
  inhouse/index.md
  inhouse/index_fixed.md  # only when an accepted fix/repair improves output
  winner/index.md
  winner/index_fixed.md   # when applicable
```

Do not replace or remove `index.md` inside adapter staging when creating a repaired or fixed candidate. Keep original adapter output available for inspection.

---

## 4. Scope discipline

- Prefer small, targeted changes over broad rewrites.
- Change only files needed for the current task.
- Avoid incidental cleanup unrelated to the requested change.
- Do not import patterns from other projects just because they seem attractive.
- Treat omissions as constraints, not creative oxygen.
- If a requirement is ambiguous and affects behavior, API shape, data shape, cost, dependency footprint, or compatibility, ask before implementing that part.
- If a small assumption is unavoidable, choose the conservative option and report it.

No cathedral-building while fixing a door hinge.

---

## 5. New files and repository hygiene

Whenever a task creates new files or directories:

- decide whether each new path belongs in Git or should be ignored,
- inspect `git status --short` before finishing,
- update `.gitignore` when new local, generated, cache, build, log, artifact, model, corpus, or machine-specific paths should stay out of Git,
- do not leave ambiguous untracked files behind,
- report the tracking decision in the completion handoff.

Never commit secrets, private corpora, model weights, downloaded archives, generated benchmark dumps, local virtualenvs, caches, or machine-specific state.

---

## 6. Testing policy

Every non-trivial code change must have tests.

Examples:

- new logic -> unit tests,
- bug fix -> regression test,
- CLI behavior -> CLI or argument-level tests,
- adapter behavior -> focused adapter or staging tests,
- QA/scoring behavior -> deterministic QA/scoring tests,
- config or orchestration change -> focused integration tests.

The default setup and test commands are:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

The default test suite must not require network access, API keys, cloud LLM credits, private corpora, local model weights, optional converter binaries, or slow external systems.

Prefer the narrowest test that proves the behavior, but run broader verification before declaring work complete.

If a full suite is already failing for unrelated reasons:

- still run the relevant suite when practical,
- report the failure exactly,
- separate pre-existing failures from task-specific failures,
- do not claim a green result.

---

## 7. Test speed is a feature

Tests should stay fast enough that agents and maintainers actually run them.

Rules:

- favor fast unit tests by default,
- avoid sleeps, real network calls, large fixtures, and heavyweight setup,
- use small synthetic fixtures for conversion edge cases,
- mock or fake external tools unless the test is explicitly integration-level,
- keep regression fixtures minimal and readable,
- treat individual tests taking more than roughly one second as suspicious unless justified,
- do not fix slow tests by simply raising timeouts.

For document-conversion bugs, prefer tiny synthetic documents or Markdown snippets that preserve the failure structure without exposing sensitive source material.

---

## 8. Documentation maintenance

Documentation is part of the deliverable.

Update docs when code changes affect:

- user-facing CLI behavior,
- output or staging shape,
- adapter behavior,
- QA/scoring behavior,
- remediation or learning-loop behavior,
- dependency footprint,
- setup, benchmarks, licensing, or troubleshooting.

Likely docs include:

- `README.md`,
- `CONTRIBUTING.md`,
- `docs/specs/*.md`,
- `docs/adapter-guide.md`,
- `docs/agent-conversion-guide.md`,
- `docs/learning-loop.md`,
- `docs/troubleshooting.md`,
- release or benchmark notes when relevant.

Do not document future behavior as if it already exists. If work is partial, say so plainly.

---

## 9. ADTM-specific engineering rules

### 9.1 Prefer deterministic checks before LLM review

Use cheap deterministic checks first. LLM review is for bounded source-fidelity auditing, not routine parsing, normalization, or repair.

### 9.2 Preserve evidence

When changing conversion, QA, scoring, repair, or remediation behavior, preserve useful evidence for later inspection. Prefer structured reports over vague strings.

Good evidence includes:

- adapter name,
- source path or document key,
- staging path,
- check names and statuses,
- before/after score summaries,
- repair or fix decision summaries,
- bounded examples of detected issues.

Avoid storing large source excerpts, sensitive content, or noisy full-document dumps.

### 9.3 Keep fixes score-guarded or quality-gated

A fix or repair should not be accepted merely because it changed text. It must improve a deterministic score or pass a narrowly defined quality gate.

When the fix changes Markdown content:

- leave original `index.md` untouched,
- write accepted improved output to `index_fixed.md` or a clearly documented sidecar,
- remove stale improved files when no fix applies,
- ensure selector and publisher behavior remain compatible.

### 9.4 Protect Markdown semantics

Conversion repairs must preserve Markdown structure unless explicitly designed to transform it.

Be conservative around:

- headings,
- lists,
- tables,
- code fences,
- blockquotes,
- images,
- captions,
- raw HTML,
- front matter,
- equations,
- page markers or provenance comments.

### 9.5 Dependency and licensing discipline

Do not add default dependencies casually.

Before adding or changing dependencies:

- check license compatibility,
- document install-footprint impact,
- keep optional converter stacks optional,
- update dependency/license notes where relevant,
- avoid commercially restricted or model-weight-heavy dependencies in the default path unless explicitly approved.

PyMuPDF licensing boundaries are already documented. Do not blur them.

---

## 10. Code style expectations

Prefer boring, readable code with sharp edges clearly labelled.

Rules:

- small functions with clear responsibilities,
- explicit names over clever abbreviations,
- dataclasses or typed parameter objects for related state,
- side effects visible at boundaries,
- public APIs stricter than internal helpers,
- comments for non-obvious intent, not for noise,
- no swallowed exceptions without a reason,
- actionable error messages.

### 10.1 File-size and gravity-well control

Avoid gravity wells: files that attract unrelated complexity until every change lands in the same swamp.

- Soft limit: keep handwritten source files under 400 lines.
- Hard limit: do not let handwritten source files exceed 600 lines unless the reason is documented.
- Split modules by responsibility before adding substantial logic to a large file.
- Generated files, lockfiles, fixture snapshots, and migration-like artifacts are exempt.

### 10.2 Function argument discipline

- Prefer five or fewer arguments per function.
- Hard limit: seven arguments maximum for internal logic.
- Boundary layers may have more wiring parameters, but deeper reusable logic should not.
- Avoid boolean flag accumulation.
- Use small typed config/result objects when state belongs together.
- Do not hide bad design inside a giant catch-all context object.

---

## 11. SABRE working protocol

When using SABRE-style implementation and review:

- one slice means one coherent behavior change,
- the implementer builds the slice,
- the reviewer red-teams the uncommitted diff,
- the reviewer does not silently patch the code they are reviewing,
- findings must be specific, reproducible, and tied to acceptance criteria,
- the implementer fixes findings or records why they are rejected,
- repeat until clean,
- commit only after implementation and review are both satisfied.

A slice should leave the repository operational. If a slice must be partial, it must leave truthful `TODO:` notes or progress docs that make the remaining work obvious without chat context.

High-risk areas need extra scrutiny:

- public API and CLI defaults,
- output shape and JSON contracts,
- scoring/ranking changes,
- dependency or license changes,
- file deletion or overwrite behavior,
- adapter orchestration,
- security, privacy, or secret-handling behavior.

---

## 12. Anti-loop discipline

Do not keep applying the same weak fix to the same evidence.

Treat a task as stalled when repeated iterations are semantically the same and failures are materially unchanged. When stalled:

- state that repetition has occurred,
- explain why prior attempts were ineffective,
- narrow the next step to one concrete experiment,
- escalate if needed.

Escalation may mean a smaller slice, a different reviewer, a synthetic repro, or human decision.

---

## 13. Completion reporting

When reporting completed work, include:

- files changed,
- behavior added or changed,
- behavior intentionally left unchanged,
- tests added or updated,
- commands run,
- documentation updated,
- assumptions made,
- new files tracked or ignored,
- remaining risks or follow-up work,
- short commit-message-style summary.

Do not claim completion unless the implementation exists, relevant tests were added or updated, verification was run, and docs were updated where reality changed.

---

## 14. What not to do

Do not:

- break backward compatibility without explicit approval,
- change defaults casually,
- require network, LLM, optional converter binaries, or private data in default tests,
- mark work complete without testing,
- rely on generated code as proof of correctness,
- make unrelated refactors during focused tasks,
- delete TODOs because work merely started,
- leave docs stale after behavior changes,
- silently change more than the task requires,
- commit generated junk or local machine state,
- hide uncertainty behind confident wording.
