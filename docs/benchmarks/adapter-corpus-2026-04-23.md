# ADTM Adapter Corpus Benchmark - 2026-04-23

This is a dated, hardware-scoped snapshot of the ADTM converter tournament.
Use it as directional evidence, not as a universal performance claim.

## Environment

- Date: `2026-04-23`
- Hardware: Intel Core i5-8400, 6 CPU cores, 15 GiB RAM
- Runtime: PRAI host environment
- Corpus: private PRAI tournament corpus
- Corpus size: `14` documents, `1505` known PDF pages
- Audit mode: `light`
- Adapter concurrency: `max_workers=4`
- Cloud/API cost: `$0` for these light-mode converter runs on `2026-04-23`
- Judge behavior: no cloud LLM judge was used for this converter matrix

Costs and speeds are date-, hardware-, dependency-, and corpus-dependent.
Cloud provider pricing can change; local runs still consume machine time.

## How To Read The Score

`mean_score` is the programmatic issue score produced by ADTM checks. Smaller is
better. A score of `0` means the programmatic checks did not find issues in that
bucket/run; it does not prove perfect Markdown.

The `quality_tier` is derived from that programmatic score and hard-gate status.
It should be read alongside wins, gate pass rate, and adapter speed.

## Side-By-Side Adapter Totals

Generated artifact (local only, not committed):
`/tmp/adtm-side-by-side-corpus-20260423/matrix.md`

| Adapter | Attempts | Gate passes | Wins | Total pages | Adapter time | Pages/sec | Mean score | Quality tier | Signal |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `inhouse` | 14 | 14 | 10 | 1505 | 35.689s | 42.170 | 2.214 | high | Keep as default |
| `docling` | 14 | 4 | 4 | 1505 | 1615.241s | 0.932 | 0.000 | high | First-class optional |
| `markitdown` | 14 | 12 | 0 | 1505 | 358.270s | 4.201 | 21.000 | medium | Optional |
| `unstructured` | 14 | 12 | 0 | 1505 | 244.220s | 6.162 | 20.417 | medium | Optional |
| `pandoc` | 14 | 1 | 0 | 1505 | 2.925s | 514.530 | 0.000 | high | Optional, limited eligibility |
| `marker` | 14 | 0 | 0 | 1505 | n/a | n/a | n/a | failed | Not available in this environment |

Interpretation:

- `inhouse` is the only current default adapter because it passed every gate,
  won most documents, and was far faster than the external adapters that were
  eligible for the same corpus.
- `docling` is worth keeping as a first-class optional adapter because it won
  several documents, but it was too slow on this corpus to run by default.
- `markitdown` and `unstructured` remain first-class optional adapters, but in
  this run neither won a document.
- `pandoc` is fast when applicable, but it was rarely eligible for this corpus.
- `marker` should stay supported as an optional adapter, but it was unavailable
  or unsupported in this environment.

## Side-By-Side By Page Bucket

| Bucket | Adapter | Attempts | Gate passes | Wins | Total pages | Adapter time | Pages/sec | Mean score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 page | `docling` | 1 | 1 | 1 | 1 | 13.051s | 0.077 | 0.000 |
| 1 page | `inhouse` | 1 | 1 | 0 | 1 | 0.004s | 250.000 | 0.000 |
| 1 page | `markitdown` | 1 | 1 | 0 | 1 | 0.983s | 1.017 | 0.000 |
| 1 page | `unstructured` | 1 | 1 | 0 | 1 | 4.735s | 0.211 | 0.000 |
| 2-10 pages | `inhouse` | 5 | 5 | 5 | 24 | 1.014s | 23.669 | 0.000 |
| 2-10 pages | `markitdown` | 5 | 5 | 0 | 24 | 9.098s | 2.638 | 14.400 |
| 2-10 pages | `unstructured` | 5 | 5 | 0 | 24 | 26.914s | 0.892 | 15.000 |
| 2-10 pages | `docling` | 5 | 0 | 0 | 24 | 70.999s | 0.338 | n/a |
| 101-1000 pages | `inhouse` | 3 | 3 | 3 | 1480 | 17.557s | 84.297 | 10.333 |
| 101-1000 pages | `markitdown` | 3 | 3 | 0 | 1480 | 338.930s | 4.367 | 60.000 |
| 101-1000 pages | `unstructured` | 3 | 2 | 0 | 1480 | 190.433s | 7.772 | 85.000 |
| 101-1000 pages | `docling` | 3 | 0 | 0 | 1480 | 1500.502s | 0.986 | n/a |
| unknown pages | `docling` | 5 | 3 | 3 | 0 | 30.689s | n/a | 0.000 |
| unknown pages | `inhouse` | 5 | 5 | 2 | 0 | 17.114s | n/a | 0.000 |
| unknown pages | `markitdown` | 5 | 3 | 0 | 0 | 9.259s | n/a | 0.000 |
| unknown pages | `pandoc` | 5 | 1 | 0 | 0 | 2.925s | n/a | 0.000 |
| unknown pages | `unstructured` | 5 | 4 | 0 | 0 | 22.138s | n/a | 0.000 |

## Current Default Smoke

After adding the PyMuPDF classifier guardrail and removing `pymupdf-layout`, the
default run was repeated with no explicit adapter list.

Generated artifact (local only, not committed):
`/tmp/adtm-default-inhouse-guardrail-20260423/matrix.md`

| Adapter | Attempts | Gate passes | Wins | Total pages | Adapter time | Pages/sec | Mean score | Quality tier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `inhouse` | 14 | 14 | 14 | 1505 | 31.297s | 48.088 | 2.214 | high |

Default smoke result:

- `14/14` documents succeeded.
- Only `inhouse` plus promoted `winner` directories were staged.
- End-to-end wall time was `136.93s`.
- No PyMuPDF `pymupdf-layout` recommendation warning appeared.
- Adapter timing and quality did not materially change from the prior no-layout
  default smoke.

## Reproduce

This snapshot used a PRAI-private corpus and host integration script that are
not part of the public package release. The committed public reproduction path
uses package-owned fixtures and is documented in
[`docs/benchmark-reproduction.md`](../benchmark-reproduction.md).

Maintainers with access to a private host corpus can reproduce an equivalent
snapshot by writing tournament staging roots with `qa_report.json` files and
then running `python -m anydoc2md.converter_benchmark_matrix` against that
staging root. Public reports should publish curated summaries only, not raw
private corpus artifacts.
