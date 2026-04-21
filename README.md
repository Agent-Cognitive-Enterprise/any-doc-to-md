# any-doc-to-md

`anydoc2md` is a shared Python package for:

- document-to-Markdown conversion
- structural and fidelity QA over conversion outputs
- multi-adapter converter tournaments
- LLM-assisted source-fidelity auditing of selected candidates

Source lives under `src/anydoc2md/`.

The canonical ADTM specification lives at
[`docs/specs/multi-method-converter-tournament.md`](docs/specs/multi-method-converter-tournament.md).
Parent projects should reference that package-owned spec instead of maintaining
their own copies.

## How It Works

`anydoc2md` owns the reusable conversion tournament itself. A typical run goes
through these stages:

1. Classify the source document to capture rough structural traits.
2. Run the requested adapters into method-scoped staging directories.
3. Hard-disqualify obviously broken outputs.
4. Run programmatic QA on surviving candidates and rank them by weighted score.
5. Select the current leading candidate.
6. Build a source evidence packet from the source document, sampling across
   the document so larger files retain first, middle, and end coverage.
7. Render the candidate Markdown to an audit PDF.
8. Audit that candidate against the source via an LLM, using the source
   evidence packet, the rendered candidate PDF, and the candidate Markdown as
   supporting detail.
9. If the LLM finds major issues, optionally build a remediation plan, persist
   findings in `.any-doc-to-md/`, penalize and rescore the candidate, and
   retry with the next ranked candidate only if the rescored candidate is no
   longer leading.
10. If the candidate passes the audit, promote it to `winner/`, optionally
   persist host-project findings, and accept the winner.

The package owns the reusable tournament logic. Host projects may optionally
persist findings and feed project-local in-house overrides back into later runs
via a local `.any-doc-to-md/` directory.

TODO: Persist a richer full-document evidence packet (likely under
`.any-doc-to-md/evidence-packets/`) rather than only embedding a bounded sampled
packet into the audit prompt.

```mermaid
flowchart TD
    A[Source document] --> B[Classify document]
    B --> C[Run tournament]
    C --> C1[inhouse]
    C --> C2[markitdown]
    C --> C3[docling]
    C --> C4[pandoc]
    C --> C5[marker]
    C1 --> D[Adapter staging dirs]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    D --> E[Run hard gates]
    E --> F[Run QA and build scorecard]
    F --> G[Select candidate]
    G --> H[Render candidate Markdown to audit PDF]
    H --> I[LLM audit against source]
    I --> J{Minor or major?}
    J -- minor --> N[Promote to winner]
    J -- major --> P[Build remediation plan optional and persist findings in .any-doc-to-md]
    P --> L[Penalize and rescore candidate]
    L --> M[Next ranked candidate]
    M --> H
    N --> O[Host project may persist findings in .any-doc-to-md]
    O --> K[Accept winner]
```

TODO: The diagram above describes the intended ADTM end-state. The current code
already has the post-selection audit loop, rendered candidate PDF generation,
winner promotion, remediation-plan persistence, project-local findings flow,
and a bounded sampled source evidence packet. The remaining gap is persisting a
richer full-document evidence packet for large documents (so escalations and
coding-agent follow-up can reference more than the in-prompt sample).

Per-adapter staging layout:

- `index.md`
- `images/`
- `adapter_result.json`

Promoted winner layout:

- `winner/index.md`
- `winner/images/`
- `winner/qa_report.json`
- `winner/remediation_plan.json` when judge findings produced one

That normalized layout is what lets the tournament compare different
converters uniformly and lets host projects ingest one stable winner path.

Audit artifacts currently added by the loop:

- source evidence packet embedded into the audit prompt
- `audit_candidate.pdf` inside the selected candidate staging dir
- `winner/qa_report.json`
- `winner/remediation_plan.json` when judge findings produced one

## Scope

This package owns reusable conversion and judging logic.

This package does not own:

- application-specific `.env` loading
- process exit behavior
- project-specific orchestration outside the shared conversion/judge surfaces

Host applications are expected to provide runtime configuration through environment variables or explicit `JudgeSettings`.

## Converter Methods

Current tournament adapters:

- `inhouse`
- `markitdown`
- `docling`
- `pandoc`
- `marker`

Adapter selection policy:

- default behavior: run all implemented adapters
- explicit adapter list: run exactly the adapters requested by the host project or user
- adapter failures such as missing CLIs are treated as candidate-level failures, not fatal tournament errors

External tools used:

| Adapter | External package / tool | Interface used | Typical input support |
|---|---|---|---|
| `inhouse` | none beyond Python libraries used internally | direct Python call | PDF, DOCX, HTML, TXT |
| `markitdown` | `markitdown` CLI | subprocess | PDF, DOCX, PPTX, XLSX, HTML, TXT, EPUB, ZIP |
| `docling` | `docling` CLI | subprocess | PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, TXT |
| `pandoc` | `pandoc` CLI | subprocess | HTML, DOCX, Markdown, TXT, RST, AsciiDoc |
| `marker` | `marker_single` CLI | subprocess | PDF |

### In-house vs External Adapters

The in-house adapter is not just a fallback. It is a first-class tournament
candidate that uses the package's own converter modules directly.

| Dimension | `inhouse` | `markitdown` | `docling` |
|---|---|---|---|
| Execution model | direct Python modules | external CLI via subprocess | external CLI via subprocess |
| Normal output shape | already aimed at package staging layout | flat Markdown file, adapter normalizes to `index.md` | `<stem>.md` plus artifacts dir, adapter normalizes to `index.md` + `images/` |
| Image handling | package-native handling, then image dimensions annotated | often little or no extracted image output for PDFs | exports referenced image files and adapter rewrites them into `images/` |
| Dependency surface | only the package + Python libs | requires installed `markitdown` CLI | requires installed `docling` CLI |
| Failure mode | Python exception path becomes structured adapter error | subprocess exit code / timeout / missing CLI | subprocess exit code / timeout / missing CLI |
| Main strength | tight integration and predictable staging semantics | broad document support and simple CLI contract | strong document-structure and image-export behavior |

### What "In-house" Means

`inhouse` wraps the package's own converter stack:

- `format_converters/pdf_converter.py`
- `format_converters/docx_converter.py`
- `format_converters/html_converter.py`
- `format_converters/txt_converter.py`

It differs from the external adapters in two important ways:

1. It does not shell out to an external converter binary.
2. It uses the package's own conversion logic directly, so layout decisions,
   normalization behavior, and staging semantics stay under package control.

The external adapters are useful as competing opinions in the tournament.
The in-house path is useful as the package-controlled baseline.

`pandoc` and `marker` are implemented adapters, not second-class placeholders.
By design, the default tournament policy should run all implemented adapters.
Hosts that want tighter control should pass an explicit adapter list instead of
relying on a partial default set.

## Project-local ADTM state

Host projects can optionally keep project-specific tournament state under a
local `.any-doc-to-md/` directory.

Supported patterns today:

- `llm-findings/<doc-key>.json` for persisted judge findings and remediation
  plans generated from tournament runs
- `inhouse-overrides/<doc-key>.override.yaml` for coding-agent-authored
  in-house conversion overrides that get staged into `document.override.yaml`
  before the in-house converter runs
- `qa-extensions/<doc-key>.py` for project-local QA hook modules that can add
  checks or disable selected built-in checks for that document
- `inhouse-extensions/<doc-key>.py` for project-local in-house post-processing
  hooks that can patch the converted staging output for that document

Deterministic scaffold authoring is also available through
`anydoc2md.remediation_authoring.author_project_local_scaffolds(...)`. It
turns a persisted remediation plan into reviewable `qa-extensions/*.py` and
`inhouse-extensions/*.py` stubs without overwriting existing files by default.

This keeps parent-project-specific ADTM learnings out of package source while
still making them easy to review or share.

### Coding-agent operating modes

Recommended split:

- read-only consumer mode: the coding agent writes document-specific hooks and
  overrides under `.any-doc-to-md/`, then reruns ADTM
- maintainer mode: the coding agent may patch package code directly, but only
  after adding a failing regression test first and rerunning the full package
  test suite

The runtime does not self-edit package code. Package maintenance remains an
explicit coding-agent or human action above the ADTM runtime.

## Audit Modes

The tournament orchestrator supports two audit modes:

- `auto`: use the LLM audit when judge settings are available; otherwise fall
  back to score-only light mode
- `light`: skip the LLM audit and accept the score-selected candidate directly

Host CLIs can expose that as a user-facing switch. PRAI's KB-pack pipeline CLI
now exposes it as `--audit-mode auto|light`.

PRAI's KB-pack pipeline CLI also supports:

- `--adtm-dir DIR` to persist findings and project-local hooks under a
  chosen `.any-doc-to-md` directory
- `--write-scaffolds` to write deterministic QA and in-house hook
  scaffold files from persisted findings

## Judge Configuration

The current LLM judge configuration is exposed via `anydoc2md.settings`.

Required environment variables:

- `ANYDOC2MD_JUDGE_URL`
- `ANYDOC2MD_JUDGE_MODEL`

Optional environment variables:

- `ANYDOC2MD_JUDGE_TIMEOUT_S`
- `ANYDOC2MD_JUDGE_MAX_TOKENS`
- `ANYDOC2MD_JUDGE_DISABLE_THINKING`
- `ANYDOC2MD_JUDGE_TEMPERATURE`

If required values are missing, the library raises `AnyDocToMdConfigError`
when loading settings explicitly, or returns an error verdict when
`judge_candidate_against_source()` or `judge_near_tie()` attempts to load them
implicitly. The tournament orchestrator's `audit_mode="auto"` path treats
missing judge settings as a signal to fall back to light mode instead of
failing the run.

## Example

```python
from anydoc2md.llm_judge import judge_candidate_against_source
from anydoc2md.settings import JudgeSettings

settings = JudgeSettings(
    url="http://127.0.0.1:1234/v1",
    model="qwen/qwen3.6-35b-a3b",
)

verdict = judge_candidate_against_source(
    candidate,
    source_path,
    traits,
    settings=settings,
)
```

## Development

The package is a normal `src/` layout project:

```bash
cd packages/any-doc-to-md
python -m pip install -e .
```

Host applications can either install the package normally or put `src/` on `PYTHONPATH` during development.

Run the package test suite directly:

```bash
cd packages/any-doc-to-md
PYTHONPATH=src pytest -q tests
```
