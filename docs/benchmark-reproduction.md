# ADTM Public Benchmark Reproduction Guide

Review date: `2026-04-24`

This guide shows how to reproduce the public benchmark workflow with only
package-owned fixtures. It intentionally avoids PRAI-private corpus paths,
cloud LLM judges, API keys, optional converter installs, and raw local
benchmark dumps.

Use this as a workflow smoke benchmark, not as a converter ranking corpus. The
small fixtures prove that tournament artifacts can be generated and aggregated
into a speed/quality matrix. The larger dated adapter snapshots in
[`docs/benchmarks/`](benchmarks/) are the directional comparison evidence.

The current public fixture set is:

- `examples/benchmark-corpus/field-note.txt`
- `examples/benchmark-corpus/ops-brief.txt`
- `src/anydoc2md/probe_assets/probe_source_reference.pdf`

## Prerequisites

From the package root:

```bash
cd packages/any-doc-to-md
python -m pip install -e ".[test]"
```

The default run below uses:

- committed public fixtures only
- default adapter set, currently `inhouse` only
- `light` audit mode
- no cloud LLM judge
- no optional external converter binaries

## Run The Public Fixture Benchmark

Create tournament artifacts under `/tmp`:

```bash
rm -rf /tmp/adtm-public-benchmark-repro
PYTHONPATH=src python - <<'PY'
import json
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT

sources = [
    Path("examples/benchmark-corpus/field-note.txt"),
    Path("examples/benchmark-corpus/ops-brief.txt"),
    Path("src/anydoc2md/probe_assets/probe_source_reference.pdf"),
]
staging_root = Path("/tmp/adtm-public-benchmark-repro")

for source in sources:
    doc_staging = staging_root / source.stem
    result = run_full_tournament(
        source,
        doc_staging,
        audit_mode=AUDIT_MODE_LIGHT,
        timeout_s=120,
    )
    if result.winner_staging_dir is None:
        raise SystemExit(f"No winner for {source}: {result.to_dict()}")

    qa_report = result.winner_staging_dir / "qa_report.json"
    qa_report.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"{source} winner={result.winner} qa_report={qa_report}")
PY
```

Generate the matrix:

```bash
PYTHONPATH=src python -m anydoc2md.converter_benchmark_matrix \
  /tmp/adtm-public-benchmark-repro \
  --sources-dir . \
  --measured-at 2026-04-24 \
  --hardware "public fixture smoke, local machine, light audit mode" \
  --output-json /tmp/adtm-public-benchmark-repro/matrix.json \
  --output-md /tmp/adtm-public-benchmark-repro/matrix.md

sed -n '1,160p' /tmp/adtm-public-benchmark-repro/matrix.md
```

Expected stable properties:

- `documents` is `3`
- `cloud_cost_usd` is `$0` for the light-mode converter run
- adapter rows contain only `inhouse` unless explicit adapters are requested
- `quality_tier` combines programmatic score with hard-gate pass rate
- the current public text fixtures land in `unknown pages`, while the committed
  probe PDF lands in `2-10 pages`
- exact seconds and pages/sec vary by hardware, OS, Python, and dependencies

The latest dated public-fixture example snapshot lives at
[`docs/benchmarks/public-fixture-corpus-2026-04-27.md`](benchmarks/public-fixture-corpus-2026-04-27.md).

Do not commit `/tmp/adtm-public-benchmark-repro` or other generated benchmark
staging roots.

## Optional Full-Pool Local Run

Run optional adapters only when the dependencies are already installed and their
license boundaries are acceptable for the environment. See
[`docs/adapter-guide.md`](adapter-guide.md) and
[`docs/dependency-license-notes.md`](dependency-license-notes.md) first.

To request every implemented adapter in the same public fixture workflow:

```python
from anydoc2md.format_converters.tournament.runner import available_adapter_names

result = run_full_tournament(
    source,
    doc_staging,
    adapters=available_adapter_names(),
    audit_mode=AUDIT_MODE_LIGHT,
    timeout_s=120,
)
```

This can be much slower than the default run and may fail adapters whose
external tools are not installed. That is useful integration evidence, but it
is not the default public benchmark contract.

## Cloud Judge Runs

Cloud judge benchmarks are opt-in. Follow
[`docs/llm-judge-setup.md`](llm-judge-setup.md) and never commit API keys,
`.env` files, request payloads containing private documents, or raw provider
responses.

When publishing cloud-backed benchmark numbers, include:

- measurement date
- provider and model name
- input and output token counts
- pricing source/date
- observed wall time and concurrency
- total spend in USD
- whether a free allowance, promotional credit, or paid balance was used

Provider prices and free allowances can change, so a cost without a date is not
actionable.

## Publishing Benchmark Summaries

Public benchmark docs should contain curated summaries, not raw staging dumps.
When adding a snapshot under `docs/benchmarks/`, include:

- date
- hardware and OS
- Python version
- package commit or release
- corpus description and whether it is public or private
- audit mode
- adapter list
- timeout and concurrency
- cloud/API cost with date, provider, model, and token context when relevant
- caveats about local time, electricity, dependency versions, and corpus bias

## Refresh Policy

Refresh release-facing benchmark numbers when any of these changes:

- converter selection, hard gates, scoring, classifier logic, or adapter code
- default adapter set or audit mode
- optional adapter dependency versions that affect conversion output
- judge provider, model, prompt, concurrency, retry behavior, or pricing
- benchmark hardware, OS, Python version, or runtime environment
- public release version
- release-facing benchmark snapshot is older than 90 days

If none of those triggers apply, older dated benchmark numbers can remain as
historical evidence, but they should not be presented as current performance.
