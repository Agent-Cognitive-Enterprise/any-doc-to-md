# any-doc-to-md

`anydoc2md` is a document-to-Markdown converter.

More precisely: it is a converter that stands on the shoulders of the best
existing conversion tools, runs them as competing candidates, asks an LLM to
help choose and validate the strongest output, and records what it learns so
future conversions can become better and faster.

It is not anti-converter. It is pro-converter, plural.

The bet is simple: no single backend wins every document. Real documents are
too varied. So `anydoc2md` treats conversion as a tournament:

- run multiple conversion methods
- normalize their outputs
- score structural quality
- localize deterministic suspect windows first, then review only those with the
  LLM for PDFs
- promote one winner
- persist findings that can drive remediation, overrides, and faster future
  decisions

That sounds simple. It is not.

Document conversion is one of those engineering problems that looks solved
until a real document arrives:

- the PDF with the figure caption attached to the wrong image
- the DOCX whose numbering restarts in the middle
- the HTML export that turns a table into decorative whitespace
- the scanned report where the converter is technically "successful" and
  practically unusable

`anydoc2md` exists because "pick one converter and hope" is not a strategy,
but neither is rebuilding the whole conversion universe from scratch. The
better move is to orchestrate strong tools, judge them rigorously, and learn
from their failures.

What the package does:

- document-to-Markdown conversion across multiple adapters
- structural and fidelity QA over conversion outputs
- tournament-style ranking and winner selection
- LLM-assisted source-fidelity auditing of selected candidates
- project-local memory for findings, overrides, and deterministic scaffolds

What makes it interesting:

- It treats conversion as an evaluation problem, not just a parsing problem.
- It uses existing converter ecosystems instead of pretending they do not
  exist.
- It preserves evidence, not just outputs.
- It gives host applications one stable winner layout even when the upstream
  tools behave very differently.
- It uses LLM review as bounded source-fidelity validation, not as magic dust.
- It is opinionated in a useful way: converters compete, artifacts are
  normalized, and failures become actionable.

Source lives under `src/anydoc2md/`.

The canonical any-doc-to-md (ADTM) specification lives at
[`docs/specs/multi-method-converter-tournament.md`](docs/specs/multi-method-converter-tournament.md).
Parent projects should reference that package-owned spec instead of maintaining
their own copies.

The package-owned judge model benchmark and current local/cloud fallback
recommendations live at
[`docs/specs/local-llm-benchmark.md`](docs/specs/local-llm-benchmark.md).

The open-source release readiness checklist lives at
[`docs/open-source-readiness.md`](docs/open-source-readiness.md).

Public project process docs:

- [`SECURITY.md`](SECURITY.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`docs/adapter-guide.md`](docs/adapter-guide.md)
- [`docs/dependency-license-notes.md`](docs/dependency-license-notes.md)
- [`docs/adapter-integration-tests.md`](docs/adapter-integration-tests.md)

If you work on ingestion, enterprise search, knowledge-base pipelines,
compliance archives, or AI/RAG systems, this package is worth understanding
because it encodes a hard-earned lesson:

> the best Markdown output is usually discovered, not assumed.

## Quick Start

Install (editable):

```bash
cd packages/any-doc-to-md
python -m pip install -e .
```

Install with test dependencies:

```bash
cd packages/any-doc-to-md
python -m pip install -e ".[test]"
```

Run the default local test suite:

```bash
python -m pytest -q
```

Run a package-only smoke conversion with the committed quickstart fixture:

```bash
python - <<'PY'
from pathlib import Path
from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

source = Path("examples/quickstart/field-note.txt")
staging = Path("/tmp/adtm-open-source-smoke")
result = run_full_tournament(source, staging, audit_mode=AUDIT_MODE_LIGHT, timeout_s=60)
assert result.winner == "inhouse", result.to_dict()
assert (staging / "winner" / "index.md").exists()
print(f"winner={result.winner} output={staging / 'winner' / 'index.md'}")
PY
```

This smoke path uses only the default `inhouse` adapter and does not call a
cloud LLM judge or external converter.

### CLI (host-provided)

`anydoc2md` is a library. Host applications usually provide the user-facing CLI
and call into the shared tournament/runtime surfaces.

In other words:

- package responsibility: convert, score, audit, normalize, persist findings
- host responsibility: environment loading, CLI UX, orchestration, exit behavior

In PRAI (this monorepo), you can run the KB-pack pipeline CLI in tournament mode:

```bash
cd backend
export ANYDOC2MD_JUDGE_PROVIDER="lm_studio"
export ANYDOC2MD_JUDGE_URL="http://127.0.0.1:1234/v1"
export ANYDOC2MD_JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
export ANYDOC2MD_JUDGE_TIMEOUT_S="360"

PYTHONPATH=. python -m source_ingestion.kb_pack_pipeline.cli --tournament --audit-mode auto \
  --adtm-dir ../.any-doc-to-md --write-scaffolds path/to/doc.pdf
```

To batch-convert the `tmp/tournament-test/sources` corpus:

```bash
cd backend
PYTHONPATH=. python scripts/convert_tournament_test_sources.py
```

To aggregate a completed tournament staging root into a dated converter
speed/quality matrix:

```bash
cd packages/any-doc-to-md
PYTHONPATH=src python -m anydoc2md.converter_benchmark_matrix \
  /tmp/adtm-side-by-side-corpus-20260423 \
  --sources-dir ../../tmp/tournament-test/sources \
  --measured-at 2026-04-23 \
  --hardware "local workstation, light audit mode" \
  --output-json /tmp/adtm-side-by-side-corpus-20260423/matrix.json \
  --output-md /tmp/adtm-side-by-side-corpus-20260423/matrix.md
```

The matrix reports wall time, pages per second, score-derived quality tiers,
win rate, and a conservative `default_set_signal` so slow adapters that never
win can be considered for the optional adapter pool instead of the default set.

To probe a local judge endpoint and find the smallest/fastest model that can
reliably surface audit issues, use the committed probe assets that ship with
the package. `find_judge` now runs in two phases:

- Phase 1 is a 10-page, text-heavy checklist packet with broken headings,
  double/dot bullets, reordered numbered lists, empty box headings, flattened
  tables, missing text, broken image references, and a figure moved away from
  its caption. The screening prompt asks the model to fill a fixed boolean
  checklist, so scoring is deterministic rather than judged by another model.
- Phase 2 takes only the Phase-1 passers and gives them a different committed
  source packet plus one committed broken candidate conversion. No checklist is
  exposed. The model audits that file in freeform JSON, and the scorer matches
  those findings against hidden gold defects plus a false-positive limit.

By default each selected model must pass both phases 10 times:

```bash
cd packages/any-doc-to-md
python -m anydoc2md.find_judge \
  --judge-url http://127.0.0.1:1234/v1 \
  --repeats 10 \
  --pass-threshold 0.6 \
  --timeout-s 30 \
  --show-all
```

For a focused run against one model:

```bash
python -m anydoc2md.find_judge \
  --judge-url http://127.0.0.1:1234/v1 \
  --model-name qwen/qwen3.6-35b-a3b \
  --repeats 10 \
  --pass-threshold 0.6 \
  --timeout-s 30 \
  --show-all
```

To rerun only Phase 2 on a known shortlist:

```bash
python -m anydoc2md.find_judge \
  --judge-url http://127.0.0.1:1234/v1 \
  --phase2-only \
  --model-name some-shortlisted-model \
  --repeats 1 \
  --timeout-s 120 \
  --show-all
```

Cloud providers can be listed and probed by setting the matching API key and
using `--judge-provider`. The CLI uses the provider default URL for explicit
cloud provider selections unless `--judge-url` is passed:

```bash
export OPENAI_API_KEY="..."
python -m anydoc2md.find_judge --judge-provider openai --list-models-only
python -m anydoc2md.find_judge \
  --judge-provider openai \
  --model-name gpt-4o-mini \
  --repeats 3 \
  --timeout-s 120 \
  --show-all
```

The same pattern works for `deepseek` with `DEEPSEEK_API_KEY` and `claude` with
`CLAUDE_API_KEY`.

For `--judge-provider openai`, the judge client starts with
`/v1/chat/completions` and automatically retries through `/v1/responses` when
OpenAI reports that the selected model is not a chat-completions model. This is
required for some Codex-oriented models. The default judge temperature is
omitted on the Responses fallback unless you explicitly override it because some
Responses-only models reject a `temperature` parameter.

The first repeat is reported as `load+answer`, which captures model-switch or
on-demand load time when the endpoint loads models lazily. Later repeats are
used to estimate steady answer time. The live progress output includes elapsed
time and ETA because this benchmark is usually a one-time hardware calibration,
not something you want to babysit blindly.

When `--repeats 1`, the probe can only report `load+answer`. Separate load and
steady-answer timing become available when `--repeats >= 2`.

The pass policy is intentionally strict: one failed repeat in either phase
disqualifies the model. `find_judge` therefore stops testing that model on the
first fail by default and continues with the next model. Passing models print a
model-level conclusion after completing all required repeats. Use
`--no-stop-on-fail` only when you want the full repeat history for diagnostics.

Failure reasons are hidden by default to keep long calibration runs readable.
Use `--show-errors` when you want diagnostic details such as JSON parse errors
or checklist misses.

The Phase-1 pass gate is configurable with `--pass-threshold`. The default is
`0.6`, which means the model must mark at least 7 of 13 expected checklist
issues and must not trigger negative controls such as OCR gibberish or
wrong-language translation. Phase 2 uses a fixed gold set on the broken
candidate: the model must surface at least 3 of 8 gold issues while staying
under the false-positive cap. `--phase2-only` skips checklist shortlisting and
runs just the freeform phase on the selected model ids.

`--timeout-s` is the production usefulness threshold for steady answer time. It
does not replace `--judge-timeout-s`, which is the HTTP read timeout. A model can
take a while to load and still be useful; a model that repeatedly takes more
than `--timeout-s` to answer after loading is excluded from the passing list.

To measure the PDF judge endpoint's safe issue-review concurrency after a model
has already passed the quality probe, run a concurrency matrix over explicit
source/audit-PDF cases. This benchmark reuses deterministic suspect
localization, then times only the bounded issue-focused judge reviews. It
records success count, wall time, input/output token usage, and observed peak
in-flight calls. For cloud providers, 429 responses are retried with
provider-aware backoff that honors `retry-after` when the provider returns it.

Example against three already-staged PRAI large-PDF winners:

```bash
cd packages/any-doc-to-md
PYTHONPATH=src python -m anydoc2md.judge_pdf_concurrency_benchmark \
  --judge-url http://127.0.0.1:1234/v1 \
  --judge-model qwen/qwen3-4b-2507 \
  --judge-timeout-s 240 \
  --concurrency-levels 1,2,4,8 \
  --case /path/to/source-a.pdf::/path/to/winner-a/audit_candidate.pdf::inhouse \
  --case /path/to/source-b.pdf::/path/to/winner-b/audit_candidate.pdf::markitdown \
  --output-json /tmp/adtm-judge-concurrency/summary.json
```

For cloud providers, set the matching API key and use `--judge-provider`:

```bash
export CLAUDE_API_KEY="..."
PYTHONPATH=src python -m anydoc2md.judge_pdf_concurrency_benchmark \
  --judge-provider claude \
  --judge-model claude-haiku-4-5-20251001 \
  --judge-timeout-s 180 \
  --concurrency-levels 2 \
  --case /path/to/source-a.pdf::/path/to/winner-a/audit_candidate.pdf::inhouse \
  --output-json /tmp/adtm-judge-concurrency/claude-summary.json
```

Use a gitignored or `/tmp` output path. Treat a single run as a functional
capacity check; use multiple repeats before choosing a production default for a
new endpoint or model. HTTP failures, malformed JSON, and parser failures count
as benchmark failures when they still fail after the per-issue retry budget is
exhausted. The JSON output includes both aggregate `tokens_used` and split
`input_tokens` / `output_tokens` fields when the provider reports them.

To estimate cloud benchmark cost from a benchmark JSON artifact, use the cost
report helper. Built-in prices are explicitly dated because provider pricing can
change:

```bash
PYTHONPATH=src python -m anydoc2md.judge_benchmark_cost_report \
  /tmp/adtm-judge-concurrency/claude-summary.json \
  --output-json /tmp/adtm-judge-concurrency/claude-cost.json
```

For models without built-in pricing, pass `--input-price-per-mtok`,
`--output-price-per-mtok`, `--priced-at`, and `--price-source-url` so the report
is auditable.

### Python

```python
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_AUTO, JudgeSettings

result = run_full_tournament(
    source_path=Path("doc.pdf"),
    staging_root=Path("staging/doc.pdf"),
    audit_mode=AUDIT_MODE_AUTO,
    judge_settings=JudgeSettings(
        url="http://127.0.0.1:1234/v1",
        model="qwen/qwen3.6-35b-a3b",
        timeout_s=360,
    ),
)
print(result.winner, result.winner_staging_dir)
```

For PDF sources, the post-selection audit now works like this:

- render the winning Markdown to a simple audit PDF
- run deterministic page-anchor comparison across the full source PDF
- if no suspicious windows are found, accept the PDF audit without an LLM call
- if suspicious windows are found, expand them into narrow local review packets
- run the judge only on those flagged packets
- retry each issue review up to three attempts when the local endpoint fails or
  returns unrepaired bad JSON
- aggregate confirmed violations into one final verdict and remediation plan

For non-PDF sources, ADTM still falls back to the older bounded evidence-packet prompt.

## Why ADTM Exists

Most conversion stacks are optimized for one of two stories:

1. "Works great on the demo file."
2. "Supports many formats."

Production systems need a third story:

3. "When the file is ugly, we still know why we trusted the output."

ADTM, short for *Any-Doc-to-Markdown Tournament*, is the package's answer to
that requirement.

The core move is deceptively strong:

- run more than one converter
- normalize the outputs into one comparable layout
- score them programmatically
- audit the leading candidate against the source with deterministic PDF suspect
  localization first
- keep the evidence and the failure reasons

This changes the operational posture of document conversion.

Instead of asking:

- "Which converter should we bless forever?"

you get to ask:

- "Which candidate won for this document, and what evidence supports that?"

That is a better question. It is more debuggable, more reviewable, and more
useful in front of users, teammates, and future-you.

## What You Learn By Reading This Package

Even if you never adopt the package whole, the design is useful:

- Normalize competing tools into one artifact contract.
- Separate *selection* from *execution*.
- Keep source-side evidence near quality decisions.
- Make LLM judgment auditable and bounded instead of mystical.
- Treat remediation output as reviewable scaffolding, not autonomous mutation.

That combination is what makes `anydoc2md` more interesting than "yet another
Markdown converter". It is a small systems design lesson wearing a practical
Python package as a disguise.

## How It Works

`anydoc2md` owns the reusable conversion tournament itself. A typical run goes
through these stages:

1. Classify the source document to capture rough structural traits.
2. Run the requested adapters into method-scoped staging directories.
3. Hard-disqualify obviously broken outputs.
4. Run programmatic QA on surviving candidates and rank them by weighted score.
5. Select the current leading candidate.
6. Render the candidate Markdown to an audit PDF.
7. For PDF sources, run deterministic source-vs-candidate checks to localize
   suspicious windows; for non-PDF sources, build a bounded source evidence
   packet.
8. If PDF checks find suspect windows, ask the LLM to review only those narrow
   issue packets. If they find nothing suspicious, accept the PDF audit without
   an LLM call. Non-PDF sources still use the bounded evidence-packet prompt.
9. If the judge finds major issues, optionally build a remediation plan, persist
   findings in `.any-doc-to-md/`, penalize and rescore the candidate, and
   retry with the next ranked candidate only if the rescored candidate is no
   longer leading.
10. If the candidate passes the audit, promote it to `winner/`, optionally
    persist host-project findings, and accept the winner.

The high-level idea is:

- conversion produces candidates
- QA produces comparable signals
- the judge produces source-aware criticism
- the runtime promotes one winner with a stable shape

That stable shape matters more than it first appears. It is what lets later
pipeline stages stop caring whether the winner came from `docling`,
`markitdown`, `pandoc`, `marker`, or the in-house converter.

The package owns the reusable tournament logic. Host projects may optionally
persist findings and feed project-local in-house overrides back into later runs
via a local `.any-doc-to-md/` directory.

When persisting project-local findings, hosts may also persist a richer source
evidence packet under `.any-doc-to-md/evidence-packets/` so escalations and
coding-agent follow-up can reference broader evidence than the in-prompt
summary.

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

The diagram above describes the intended ADTM end-state. The current code
already has the post-selection audit loop, rendered candidate PDF generation,
winner promotion, remediation-plan persistence, project-local findings flow,
deterministic PDF suspect localization, narrow issue-focused LLM review for
flagged PDF regions, and both a bounded in-prompt source evidence packet and an
optional persisted evidence packet for offline review.

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

- localized PDF issue packets embedded into narrow review prompts when
  deterministic checks flag suspicious windows
- bounded source evidence packet embedded into the audit prompt for non-PDF
  sources
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
- `unstructured`
- `pandoc`
- `marker`

Adapter selection policy:

- default behavior: run `inhouse` only
- explicit adapter list: run exactly the adapters requested by the host project or user
- benchmark/all-adapter runs: pass an explicit all-adapter list from
  `available_adapter_names()` or use the parent PRAI script's `--adapters all`
- adapter failures such as missing CLIs are treated as candidate-level failures, not fatal tournament errors

External tools used:

| Adapter | External package / tool | Interface used | Typical input support |
|---|---|---|---|
| `inhouse` | none beyond Python libraries used internally | direct Python call | PDF, DOCX, HTML, TXT |
| `markitdown` | `markitdown` CLI | subprocess | PDF, DOCX, PPTX, XLSX, HTML, TXT, EPUB, ZIP |
| `docling` | `docling` CLI | subprocess | PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, TXT |
| `unstructured` | `unstructured` Python package | subprocess-backed Python module | PDF, DOCX, PPTX, XLSX, HTML, TXT, Markdown, RTF, EPUB, XML, JSON, CSV, TSV |
| `pandoc` | `pandoc` CLI | subprocess | HTML, DOCX, Markdown, TXT, RST, AsciiDoc |
| `marker` | `marker_single` CLI | subprocess | PDF |

### In-house vs External Adapters

The in-house adapter is not just a fallback. It is a first-class tournament
candidate that uses the package's own converter modules directly.

All adapters are normalized into the same staging layout (`index.md`, `images/`,
and `adapter_result.json`) so the tournament can score and audit them uniformly.
The main differences are the conversion engine, image extraction behavior, and
dependency footprint.

| Dimension | `inhouse` | `markitdown` | `docling` | `unstructured` | `pandoc` | `marker` |
|---|---|---|---|---|---|---|
| Execution model | direct Python modules | external CLI via subprocess | external CLI via subprocess | subprocess-backed Python module | external CLI via subprocess | external CLI via subprocess |
| Normal output shape | already aimed at package staging layout | flat Markdown output, adapter writes `index.md` | `<stem>.md` + artifacts dir, adapter normalizes to `index.md` + `images/` | ordered elements rendered back into `index.md` | adapter writes `index.md` | marker output normalized into `index.md` + `images/` |
| Image handling | package-native staging + image-dimension annotation when images are present | typically no extracted image files; `images/` often empty | exports referenced image files and adapter rewrites them into `images/` | does not currently extract image files; `images/` stays empty | does not extract images; creates `images/` but leaves it empty | extracts images for PDFs and rewrites paths into `images/` |
| Dependency surface | only the package + Python libs | requires installed `markitdown` CLI | requires installed `docling` CLI | requires `unstructured[all-docs]` plus upstream system deps for some formats | requires installed `pandoc` CLI | requires installed `marker_single` CLI |
| Failure mode | Python exception becomes structured adapter error | subprocess exit code / timeout / missing CLI | subprocess exit code / timeout / missing CLI | subprocess exit code / timeout / missing package | subprocess exit code / timeout / missing CLI | subprocess exit code / timeout / missing CLI |
| Main strength | tight integration and predictable staging semantics | broad input support and simple CLI contract | strong document-structure and image-export behavior | broad partitioning coverage and table/OCR-oriented ecosystem | deterministic normalizer for text-centric formats | strong layout retention for PDFs |

Note: `pandoc` and `marker` are GPL-licensed external tools. Review their terms
before enabling them in commercial or redistributable pipelines.

Note: `unstructured` is now an experimental implemented adapter. ADTM currently
routes PDFs through Unstructured's text-first `fast` strategy rather than the
default OCR/layout-heavy auto path so the adapter remains usable on hosts
without `tesseract`. Upstream docs still recommend
`pip install 'unstructured[all-docs]'` plus system dependencies such as
`libmagic`, `poppler`, `tesseract`, and `libreoffice` depending on the file
types you want to process.

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
`markitdown`, `docling`, `unstructured`, `pandoc`, and `marker` remain
first-class optional adapters: they are documented, tested, benchmarkable, and
selectable by explicit adapter list. The default runtime set is intentionally
`inhouse` only until dated benchmark evidence justifies adding another adapter
back to the default path. This keeps normal conversions fast while preserving
the full multi-adapter tournament for explicit benchmark or diagnostic runs.

A dated adapter comparison snapshot is maintained in
[`docs/benchmarks/adapter-corpus-2026-04-23.md`](docs/benchmarks/adapter-corpus-2026-04-23.md).
It records the 2026-04-23 side-by-side corpus matrix, hardware context, cost
context, and reproduction commands.

Public adapter selection, install boundaries, image behavior, and when-to-use
guidance live in [`docs/adapter-guide.md`](docs/adapter-guide.md).
Optional adapter install boundaries and local smoke commands are documented in
[`docs/adapter-integration-tests.md`](docs/adapter-integration-tests.md).
Dependency and license notes, including the required PyMuPDF AGPL/commercial
release-audit item, are documented in
[`docs/dependency-license-notes.md`](docs/dependency-license-notes.md).

2026-04-23 corpus snapshot, measured on an Intel Core i5-8400 with 6 CPU cores
and 15 GiB RAM in `light` audit mode:

Cloud/API cost for this specific table: `$0` on `2026-04-23` (light mode; no
cloud LLM judge).

| Adapter | Attempts | Gate passes | Wins | Total pages | Adapter time | Pages/sec | Mean score | Recommendation |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `inhouse` | 14 | 14 | 10 | 1505 | 35.689s | 42.170 | 2.214 | Default |
| `docling` | 14 | 4 | 4 | 1505 | 1615.241s | 0.932 | 0.000 | First-class optional |
| `markitdown` | 14 | 12 | 0 | 1505 | 358.270s | 4.201 | 21.000 | Optional |
| `unstructured` | 14 | 12 | 0 | 1505 | 244.220s | 6.162 | 20.417 | Optional |
| `pandoc` | 14 | 1 | 0 | 1505 | 2.925s | 514.530 | 0.000 | Optional, limited eligibility |
| `marker` | 14 | 0 | 0 | 1505 | n/a | n/a | n/a | Not available in this environment |

Smaller `mean_score` is better. This table is date-, hardware-, corpus-, and
dependency-dependent; provider pricing and cloud costs can change over time.

## Project-local ADTM state

Host projects can optionally keep project-specific tournament state under a
local `.any-doc-to-md/` directory.

Supported patterns today:

- `llm-findings/<doc-key>.json` for persisted judge findings and remediation
  plans generated from tournament runs
- `evidence-packets/<doc-key>.json` for richer persisted source evidence packets
  referenced from `llm-findings` records
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

- `ANYDOC2MD_JUDGE_MODEL`

Optional environment variables:

- `ANYDOC2MD_JUDGE_PROVIDER` (`lm_studio`, `openai`, `deepseek`, or `claude`;
  defaults to `lm_studio`)
- `ANYDOC2MD_JUDGE_URL`; required for `lm_studio`, optional for cloud providers
  because provider defaults are built in
- `ANYDOC2MD_JUDGE_TIMEOUT_S`
- `ANYDOC2MD_JUDGE_MAX_TOKENS`
- `ANYDOC2MD_JUDGE_DISABLE_THINKING`
- `ANYDOC2MD_JUDGE_TEMPERATURE`
- `ANYDOC2MD_JUDGE_PDF_CONCURRENCY`
- `OPENAI_API_KEY` when `ANYDOC2MD_JUDGE_PROVIDER=openai`
- `DEEPSEEK_API_KEY` when `ANYDOC2MD_JUDGE_PROVIDER=deepseek`
- `CLAUDE_API_KEY` when `ANYDOC2MD_JUDGE_PROVIDER=claude`

Provider defaults:

- `lm_studio`: OpenAI-compatible chat completions at `ANYDOC2MD_JUDGE_URL`
- `openai`: `https://api.openai.com/v1`; the client automatically falls back to
  `/v1/responses` for OpenAI models that reject `/v1/chat/completions`
- `deepseek`: `https://api.deepseek.com/v1`
- `claude`: `https://api.anthropic.com/v1/messages`

PDF issue reviews are bounded and run concurrently up to
`ANYDOC2MD_JUDGE_PDF_CONCURRENCY`, which defaults to `4`. Set it to `1` for
strictly serial local-judge calls or lower-resource endpoints.

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
    provider="lm_studio",
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
