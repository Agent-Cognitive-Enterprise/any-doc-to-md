# Multi-method converter tournament — implementation spec

**Status:** Draft — partially implemented, not yet signed off  
**Scope:** `anydoc2md` shared package, document -> Markdown conversion layer  
**Module location:** `packages/any-doc-to-md/src/anydoc2md/`

## Source of truth

This document is the canonical ADTM specification.

- Package behavior should be documented here first.
- Parent projects such as PRAI should reference this spec rather than maintain a separate copy.
- If this spec and current code differ, treat the current code as the implemented baseline and this document as the intended next-state design.

## Current implementation snapshot

This document mixes two things:

- the target tournament design
- the subset that is already implemented in `anydoc2md`

Implemented today:

- shared `AdapterResult` contract
- classifier heuristics
- `inhouse`, `markitdown`, `docling`, `pandoc`, and `marker` adapters
- adapter-selection policy where the default tournament runs all implemented adapters unless the host passes an explicit adapter list
- parallel tournament runner
- hard gates for missing/empty output, broken image refs, charset plausibility, and sampled PDF text coverage
- weighted programmatic QA scoring
- score-based candidate selection
- post-selection LLM audit loop over ranked candidates, with deterministic PDF suspect localization plus narrow issue-focused review for PDF sources and bounded fallback evidence for non-PDF sources
- major-finding penalty and rescore of the currently audited candidate before advancing to the next ranked candidate
- `auto` vs `light` audit modes, where `auto` falls back to score-only selection if no judge is configured
- persisted ADTM findings under project-local `.any-doc-to-md/` state when the host project enables it
- staged project-local `qa_extension.py` and `inhouse_extension.py` hooks loaded from `.any-doc-to-md/` in read-only consumer mode
- winner promotion into a stable `winner/` staging dir

Still planned, not implemented yet:

- the richer violation schema described below (`severity`, `violation_type`, `confidence` per programmatic check)
- coding-agent execution of remediation retries inside the package runtime
- automated coding-agent extension authoring from judge findings
- coding-agent maintainer-vs-read-only operating modes
- `MinerU` adapter
- human escalation packet generation

---

## Goal

Build a **multi-method conversion tournament** that runs N converters against the same source document, evaluates each candidate with weighted QA scoring, selects the current best candidate, audits that candidate against the source with an LLM, and self-improves by codifying failures as programmatic tests.

Optimise for:
- preserved reading order
- image-to-text proximity and association
- preserved section/heading hierarchy
- minimal missing or duplicated content
- robustness across multi-column, scanned, table-heavy, and layout-complex documents

Do **not** optimise for pixel-perfect layout recreation. Semantic flow matters; visual fidelity does not.

---

## Architecture overview

```text
Stage 0: Document classification
Stage 1: Multi-method conversion tournament (run N converters in parallel)
Stage 2: Hard disqualification gates (blank output, major content loss, etc.)
Stage 3: Weighted QA scoring (structured violation report per candidate)
Stage 4: Candidate selection (lowest weighted score, log losers)
Stage 5: LLM source-fidelity audit of the selected candidate
Stage 6: Penalty/rescore current candidate and continue only if it no longer leads
Stage 7: Fix-learning loop (coding agent codifies failures as tests + rules)
Stage 8: Human escalation (if max retries exhausted)
```

---

## Module layout (target)

```text
anydoc2md/
  format_converters/
  adapters/
    base.py          <- AdapterResult dataclass; adapter protocol
    markitdown.py    <- subprocess wrapper: markitdown input -o output.md
    docling.py       <- subprocess wrapper: docling input --to md --output ./out
    marker.py        <- subprocess wrapper: marker_single input --output_format markdown
    pandoc.py        <- subprocess wrapper: pandoc -f <fmt> -t markdown
    inhouse.py       <- delegates to existing pdf/docx/html/txt converters
  classification/
    classify_document.py   <- DocumentTraits; fitz-backed for PDFs
  tournament/
    runner.py        <- run_tournament(source_path, adapters) -> list[AdapterResult]
    selector.py      <- select_candidate(candidates, qa_results) -> SelectionResult
    scoring.py       <- weighted_score(qa_result) -> float
    audit.py         <- source-vs-rendered-candidate LLM audit loop
    remediation.py   <- findings -> remediation plan
    # existing modules unchanged:
    base.py          <- ConversionResult (extend with severity on CheckResult)
    pdf_converter.py
    docx_converter.py
    html_converter.py
    txt_converter.py
    __init__.py
```

The `output_qa/` module grows:

```text
output_qa/
  checks.py      <- extend CheckResult: add severity, violation_type, confidence
  scoring.py     <- weighted_score(), ViolationWeights config
  runner.py      <- return weighted score alongside passed: bool
  hard_gates.py  <- fast disqualification checks (blank, coverage collapse)
```

---

## Converter pool

### Implemented adapters

| Converter | License | Primary use case | CLI |
|---|---|---|---|
| MarkItDown | MIT | Broad default, office/general docs | `markitdown input.pdf -o output.md` |
| Docling | MIT | General high-fidelity (PDF, DOCX, tables) | `docling input.pdf --to md --output ./out` |
| Marker | GPL-3.0 + model terms | Specialist: complex layout, equations, tables | `marker_single input.pdf --output_format markdown --output_dir ./out` |
| Pandoc | GPL-2.0+ | Deterministic normaliser for structured formats | `pandoc -f <fmt> -t markdown` |
| In-house | Internal | First-class candidate; existing converters | existing `pdf_converter`, `html_converter`, etc. |

Default selection behavior should use every implemented adapter above.
If a host project or user passes an explicit adapter list, the tournament should
run exactly that list instead.

### Planned adapters

| Converter | License | Primary use case | Status |
|---|---|---|---|
| MinerU | Custom Apache 2.0 | OCR-heavy, scanned PDFs | planned V2 |

### Optional helper tools

| Tool | License | Primary use case |
|---|---|---|
| PyMuPDF4LLM | AGPL-3.0 | Lightweight PDF fallback/analysis helper |

### Licensing notes

- **MarkItDown (MIT)** and **Docling (MIT)**: safe for any deployment.
- **Marker (GPL-3.0)**: CLI invocation from a non-GPL process (subprocess boundary) is generally fine, but requires explicit legal review before deep embedding or library import. The model weights have additional licensing terms.
- **Pandoc (GPL-2.0+)**: same subprocess-boundary reasoning as Marker; safe to invoke as a tool.
- **MinerU**: custom open-source licence based on Apache 2.0 with additional terms; review before committing.

---

## Stage 0: Document classification

Before conversion, classify the source document to route efficiently.

```python
@dataclass(frozen=True)
class DocumentTraits:
    is_scanned: bool
    is_born_digital: bool
    is_multicolumn: bool
    has_text_boxes_or_sidebars: bool
    is_table_heavy: bool
    is_equation_heavy: bool
    is_image_dense: bool
    has_captions: bool
    language_guess: str
    page_count: int
    extractable_text_ratio: float
```

Routing hints are soft, not hard rules:

- Office/general: MarkItDown first
- Complex PDF / tables / equations: Docling or Marker
- Scanned / OCR-heavy: MinerU or Marker + OCR
- HTML / DOCX / structured: Pandoc as normaliser or primary
- Unknown: run full pool

If classification is uncertain, run the full pool. Classification is cheap; bad conversion is expensive.

---

## Stage 1: AdapterResult schema

Each converter outputs a structured result:

```python
@dataclass(frozen=True)
class AdapterResult:
    method_name: str
    method_version: str
    command_invoked: str
    exit_code: int
    markdown_path: Path | None
    assets_dir: Path | None
    staging_dir: Path
    timing_ms: int
    stderr: str
    status: str
```

Staging dir layout per method:

```text
staging_root/{doc_id}/{method_name}/
    index.md
    images/
    adapter_result.json
```

---

## Stage 2: Hard disqualification gates

Fast checks eliminate clearly broken outputs before scoring.

A candidate fails hard gates if any of the following is true:

- output is blank or under 100 characters
- text coverage vs. source is under 30% for born-digital PDFs
- more than 50% of source headings are missing from output
- Markdown parse/render raises an error
- broken image references leave all image targets missing
- massive duplication repeats any block over 200 chars more than 3 times
- catastrophic reading-order collapse is detected via heading sequence regression

Hard-gate failures are logged as `status: "hard_fail"` in the QA result and excluded from scoring. If all candidates fail hard gates, escalate immediately.

---

## Stage 3: Weighted QA scoring

QA produces a structured violation report per candidate.

### Violation classes and weights

```python
VIOLATION_WEIGHTS = {
    "missing_content": 9,
    "reading_order": 8,
    "duplicated_content": 7,
    "image_text_association": 7,
    "caption_detachment": 6,
    "table_fragmentation": 5,
    "heading_hierarchy": 4,
    "footnote_displacement": 3,
    "orphan_image": 3,
    "formatting_only_minor": 1,
}

SEVERITY_WEIGHTS = {
    "critical": 10,
    "major": 4,
    "minor": 1,
}
```

### Score formula

```text
candidate_score =
    sum(VIOLATION_WEIGHTS[type] * SEVERITY_WEIGHTS[severity] * count)
  + uncertainty_penalty
  + catastrophic_penalty
```

Lower score is better.

---

## Stage 4: Candidate selection

Programmatic QA selects the current leading candidate. This is not yet the final winner.

Selection policy:

- choose the lowest-scoring surviving candidate
- log disqualified and losing candidates
- keep ranking order for retry
- stop early only if no viable candidates remain

The score-selected leader is only a candidate until the source-fidelity audit passes. The runtime now exposes `select_candidate`, while keeping `select_winner` as a backward-compatible alias.

---

## Stage 5: LLM source-fidelity audit

After programmatic selection, audit the current leading candidate against the source.

Preferred comparison surface:

- source PDF vs rendered PDF from candidate Markdown when source is a PDF
- source document vs rendered PDF from candidate Markdown for non-PDF inputs when a unified visual audit surface is needed

The LLM should return structured findings, not only prose.

Example shape:

```json
{
  "overall_severity": "major",
  "findings": [
    {
      "type": "reading_order",
      "severity": "major",
      "pages": [3, 4],
      "evidence": "Paragraph following Figure 2 appears before its lead-in text."
    }
  ],
  "score_penalty": 18,
  "should_disqualify": false
}
```

Suggested control flow:

1. rank candidates programmatically
2. select current leading candidate
3. render candidate Markdown to audit PDF
4. run LLM audit against source unless the host selected light mode
5. if only minor issues are found, promote and accept winner
6. if major issues are found, persist findings and rescore the current candidate with an LLM penalty
7. if the rescored candidate still leads, accept it with findings; otherwise move to the next ranked candidate
8. allow at most 3 LLM audits per document
9. escalate to human review when the audit budget is exhausted

The current implementation now runs this post-selection audit loop, renders a simple audit PDF from candidate Markdown, and, for PDF sources, first runs deterministic page-anchor checks across the full source and candidate PDFs. If those checks find no suspicious windows, the PDF audit short-circuits without an LLM call. If they do find suspicious windows, ADTM expands those windows into narrow issue packets, asks the LLM to review only those localized suspects with configurable bounded concurrency (default `4`), and aggregates the confirmed violations into one final verdict with page-scoped evidence. Non-PDF sources still use the older bounded evidence-packet prompt. Host workflows may also persist a richer source evidence packet under `.any-doc-to-md/evidence-packets/` for offline review and coding-agent follow-up.

---

## Stage 6: Fix-learning loop

The fix-learning loop has two operating modes.

### LLM-only mode

When no coding agent is available:

- persist findings under `.any-doc-to-md/`
- keep project-local evidence and remediation notes sharable through normal GitHub workflows
- continue candidate reselection or escalate after retry budget is exhausted

### LLM plus coding-agent mode

When a coding agent is available, it sits above ADTM rather than inside it.

Expected flow:

1. a parent workflow such as PRAI KB pack builder selects source documents
2. the coding agent runs ADTM CLI to convert them
3. ADTM emits findings and writes detailed issue descriptions under `.any-doc-to-md/`
4. the coding agent reads those findings
5. the coding agent creates QA extensions or replacements and in-house converter extensions or replacements
6. the coding agent reruns ADTM and verifies the issue is resolved without regressions

The coding agent should not blindly patch package code from raw LLM prose. It should consume structured findings, add a failing regression test first, implement the narrowest safe fix, rerun focused tests, rerun full package tests in maintainer mode, and rerun ADTM on the original offending document.

### Coding-agent operating modes

The coding agent should distinguish between:

- `readonly_consumer`
- `maintainer_writable`

#### Read-only consumer mode

When the package is installed read-only:

- do not patch package source
- store project-local extensions, overrides, and findings under `.any-doc-to-md/`
- rely on staged document-root files such as `document.override.yaml`, `qa_extension.py`, and `inhouse_extension.py`
- prefer additive extensions over full replacements

#### Maintainer writable mode

When the package checkout is writable and the session is acting as a maintainer:

- the coding agent may patch `anydoc2md` directly
- it must add or update regression tests first
- it must run the full package suite before completion
- it must rerun ADTM on the original problematic document

Suggested direct-patch guardrails:

- maintainer mode must be explicit
- the issue must be reproduced
- the issue must look package-general, not just document-specific
- a failing regression test must be added first
- the full package suite must pass afterward

If any of those checks fail, fall back to project-local `.any-doc-to-md/` extensions instead of editing package code.

---

## Stage 7: Human escalation

Escalate when:

- all candidates fail hard gates
- the LLM audit budget is exhausted
- findings are high severity but not safely codifiable
- the coding agent cannot produce a deterministic fix without unsafe replacement behavior

Escalation output should include:

- source document identity
- candidate ranking summary
- structured findings
- evidence packet references
- retry count and audit count
- whether the issue appears project-local or package-general

---

## Project-local ADTM state

Host projects can keep project-specific tournament state under `.any-doc-to-md/`.

Supported patterns today:

- `llm-findings/<doc-key>.json` for persisted judge findings and remediation plans
- `evidence-packets/<doc-key>.json` for richer persisted source evidence packets referenced from `llm-findings`
- `inhouse-overrides/<doc-key>.override.yaml` for coding-agent-authored in-house conversion overrides that get staged into `document.override.yaml`
- `qa-extensions/<doc-key>.py` for document-local QA hook modules that can add checks or disable selected built-in checks
- `inhouse-extensions/<doc-key>.py` for document-local in-house post-processing hooks

Deterministic scaffold authoring is implemented via
`anydoc2md.remediation_authoring.author_project_local_scaffolds(...)`, which
translates persisted remediation plans into reviewable hook stubs without
overwriting existing local files by default.

This keeps parent-project-specific ADTM learnings out of package source while still making them easy to review or share.

---

## Verification expectations

Any meaningful ADTM change should be validated at the narrowest useful layer first, then at broader package scope.

For maintainer-mode coding-agent changes, require:

- a focused regression test for the exact defect
- rerun of affected package tests
- rerun of the full `packages/any-doc-to-md` suite
- rerun of ADTM on the original offending document

For parent-workflow integration changes, also rerun the relevant backend integration or end-to-end coverage.
