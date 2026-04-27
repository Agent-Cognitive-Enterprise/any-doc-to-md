# ADTM Public Fixture Benchmark Snapshot

Measurement date: `2026-04-27`

- Package scope: `packages/any-doc-to-md`
- Corpus: package-owned public fixture set
- Corpus members:
  - `examples/benchmark-corpus/field-note.txt`
  - `examples/benchmark-corpus/ops-brief.txt`
  - `src/anydoc2md/probe_assets/probe_source_reference.pdf`
- Adapter set: default only, currently `inhouse`
- Audit mode: `light`
- Judge provider: none
- Cloud/API cost: `$0` on `2026-04-27`
- Python: `3.13.13`
- OS/kernel: `Linux 6.8.0-110-generic x86_64`
- Hardware: `Intel Core i5-8400 (6 cores / 6 threads), local run`

This snapshot is a public benchmark smoke, not a broad winner-selection corpus.
It proves that the benchmark pipeline, tournament artifacts, and matrix
aggregation run from a clean package checkout without private PRAI inputs.

## Matrix

```md
# ADTM Converter Benchmark Matrix

- measured_at: `2026-04-27`
- hardware: `Intel Core i5-8400 (6 cores / 6 threads), Python 3.13.13, Linux 6.8.0-110-generic x86_64, local run, light audit mode`
- staging_root: `/tmp/adtm-public-benchmark-repro-20260427`
- documents: `3`
- cloud_cost_usd: `$0` for this light-mode converter run

## By Page Bucket And Adapter

| bucket | adapter | attempts | total_pages | total_time_s | raw_successes | gate_passes | wins | raw_success_rate | gate_pass_rate | win_rate | mean_time_s | median_time_s | pages_per_second | mean_score | quality_tier | default_set_signal | cloud_cost_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2-10 pages | inhouse | 1 | 10 | 0.01 | 1 | 1 | 1 | 1.0 | 1.0 | 1.0 | 0.01 | 0.01 | 1000.0 | 30.0 | medium | keep_default_candidate | 0.0 |
| unknown pages | inhouse | 2 | 0 |  | 2 | 2 | 2 | 1.0 | 1.0 | 1.0 |  |  |  | 0.0 | high | keep_default_candidate | 0.0 |

## Adapter Totals

| adapter | attempts | total_pages | total_time_s | raw_successes | gate_passes | wins | raw_success_rate | gate_pass_rate | win_rate | mean_time_s | median_time_s | pages_per_second | mean_score | quality_tier | default_set_signal | cloud_cost_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| inhouse | 3 | 10 | 0.01 | 3 | 3 | 3 | 1.0 | 1.0 | 1.0 | 0.01 | 0.01 | 1000.0 | 10.0 | high | keep_default_candidate | 0.0 |

## Documents

| document_id | bucket | file_type | page_count | word_count | winner | winner_score | adapter_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| examples/benchmark-corpus/field-note.txt | unknown pages | txt | 0 | 65 | inhouse | 0.0 | 1 |
| examples/benchmark-corpus/ops-brief.txt | unknown pages | txt | 0 | 82 | inhouse | 0.0 | 1 |
| src/anydoc2md/probe_assets/probe_source_reference.pdf | 2-10 pages | pdf | 10 | 1006 | inhouse | 30.0 | 1 |
```

## Notes

- Times and pages/sec are hardware-, dependency-, and runtime-dependent.
- Local runs still consume CPU time and electricity even when cloud cost is
  `$0`.
- This corpus is intentionally small and should not be treated as a general
  converter ranking benchmark.
- The current traits pipeline reports `page_count=0` for the plain-text
  fixtures, so they land in the `unknown pages` bucket in the matrix. That is
  acceptable for this release-smoke corpus because the benchmark goal here is
  reproducibility, not page-bucket coverage across every format.
- For the broader dated side-by-side comparison, see
  [`adapter-corpus-2026-04-23.md`](adapter-corpus-2026-04-23.md).
