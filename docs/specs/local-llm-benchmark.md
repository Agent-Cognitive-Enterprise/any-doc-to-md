# ADTM LLM Judge Benchmark

## Purpose

Define the benchmark contract and current measured model choices for the
`anydoc2md` LLM judge.

This document is package-owned because ADTM owns:

- `python -m anydoc2md.find_judge`
- `python -m anydoc2md.judge_pdf_concurrency_benchmark`
- the PDF audit prompt and parser contract
- deterministic suspect localization and bounded issue-review packets
- judge provider configuration for local and cloud endpoints

Parent projects may link here, but should not duplicate these ADTM-specific
model-selection results.

## Required Judge Gates

For ADTM document-conversion judge use, a model must pass the package-owned
judge probes and concurrency-capacity check before it is treated as a production
candidate:

- `python -m anydoc2md.find_judge` for checklist and hidden freeform quality
- `python -m anydoc2md.judge_pdf_concurrency_benchmark` for issue-review
  concurrency levels such as `1,2,4,8`

The judge concurrency benchmark is endpoint-specific. Record the hardware,
model id, context window, concurrency level, success rate, wall time, token
usage, and observed peak in-flight calls before raising
`ANYDOC2MD_JUDGE_PDF_CONCURRENCY` above the default.

Malformed JSON is a model/reliability failure even when the endpoint accepts
concurrent HTTP requests. Require repeated clean runs before changing the
production default.

## Local Judge Snapshot, 2026-04-22

This snapshot records the current local LM Studio endpoints used for PDF judge
selection. It is not a permanent model ranking; rerun the same probes when the
model build, runtime, context window, hardware, or prompt contract changes.

Test endpoints:

- `.57`: RTX 4080 class host, 16GB VRAM, 64GB RAM, 8k context window
- `.59`: GTX 1070 class host, 8GB VRAM, 64GB RAM, 8k context window

Measured outcome:

- `.57` quality probes: `qwen/qwen3-4b-2507`, `qwen/qwen3-14b`,
  `qwen/qwen3-30b-a3b-2507`, and `mistralai/mistral-small-3.2` passed the
  repeated checklist and freeform judge probes. `google/gemma-4-e4b` failed
  repeated freeform due to false positives; `openai/gpt-oss-20b` failed repeat
  stability with non-JSON output.
- `.57` retry-enabled real-PDF issue review: `qwen/qwen3-4b-2507` is now the
  practical default candidate at `c=4`. It passed the clinical PDF repeat
  `10/10`, mean `13.828s`, and the three representative PDFs `3/3`, mean
  `14.349s`. Earlier pre-retry clinical runs produced malformed JSON, so keep
  per-issue retry enabled and rerun this gate when prompts, parser behavior, or
  runtime settings change.
- `.57` conservative fallback: warm `qwen/qwen3-30b-a3b-2507` at `c=4` also
  passed cleanly with the retry-enabled path: clinical repeat `3/3`, mean
  `39.361s`; three representative PDFs `3/3`, mean `45.025s`. It remains useful
  when quality margin is valued over speed, but it is roughly three times slower
  on the measured real-PDF issue-review workload.
- `.59` retry-enabled real-PDF issue review: `qwen3-4b-instruct-2507` remains
  the constrained-GPU fallback at `c=2`. It passed the clinical PDF repeat
  `10/10`, mean `61.805s`, and the three representative PDFs `3/3`, mean
  `58.052s`, with observed `max_active_calls=2`.

Current local recommendations:

- Use `.57` `qwen/qwen3-4b-2507` with `ANYDOC2MD_JUDGE_PDF_CONCURRENCY=4` as
  the practical local PDF judge default when the retry-enabled issue reviewer is
  available.
- Keep warm `.57` `qwen/qwen3-30b-a3b-2507` with
  `ANYDOC2MD_JUDGE_PDF_CONCURRENCY=4` as the conservative fallback.
- Use `.59` `qwen3-4b-instruct-2507` with
  `ANYDOC2MD_JUDGE_PDF_CONCURRENCY=2` as the constrained-GPU fallback.
- Re-run the same real-PDF repeat gate before changing either the model id,
  context window, retry behavior, prompt contract, or LM Studio runtime.

Artifacts from this run were written outside git under:

- `/tmp/adtm-judge-model-selection/`
- `/tmp/adtm-judge-concurrency-matrix/`
- `/tmp/adtm-judge-validation/`
- `/tmp/adtm-judge-validation-concurrent/`
- `/tmp/adtm-judge-retry-validation/`

## Cloud Judge Snapshot, 2026-04-22

Cloud providers are optional fallbacks for environments where local judge
quality, latency, or hardware availability is insufficient. They must not
replace the offline-first local path as the default product assumption.

Provider model listing checks:

- `openai`: `python -m anydoc2md.find_judge --judge-provider openai --list-models-only`
  returned 122 model ids from `https://api.openai.com/v1/models`.
- `deepseek`: `python -m anydoc2md.find_judge --judge-provider deepseek --list-models-only`
  returned `deepseek-chat` and `deepseek-reasoner`.
- `claude`: `python -m anydoc2md.find_judge --judge-provider claude --list-models-only`
  returned 9 model ids from `https://api.anthropic.com/v1/models`.

Measured `find_judge` stability checks, all with `--repeats 3`,
`--timeout-s 120`, and `--judge-timeout-s 180`:

- Claude `claude-haiku-4-5-20251001`: checklist `3/3`, answer mean `1.54s`,
  max `1.55s`, mean tokens `1963`; freeform `3/3`, answer mean `4.52s`, max
  `4.58s`, mean tokens `1366`.
- OpenAI `gpt-4o-mini`: checklist `3/3`, answer mean `2.81s`, max `3.14s`,
  mean tokens `1656`; freeform `3/3`, answer mean `8.44s`, max `10.14s`, mean
  tokens `878`.
- DeepSeek `deepseek-chat`: checklist `3/3`, answer mean `7.98s`, max `8.18s`,
  mean tokens `1739`; freeform `3/3`, answer mean `28.45s`, max `28.93s`, mean
  tokens `1154`.

Current cloud fallback order:

- Use Claude `claude-haiku-4-5-20251001` as the fastest measured cloud fallback
  on this probe.
- Use OpenAI `gpt-4o-mini` as the second measured cloud fallback; it was slower
  than Haiku but well inside the `120s` production usefulness threshold.
- Use DeepSeek `deepseek-chat` when DeepSeek is preferred operationally; it
  passed cleanly but was materially slower on the freeform phase.

Cloud probe artifacts from this run were written outside git under:

- `/tmp/adtm-cloud-judge-probes/`
