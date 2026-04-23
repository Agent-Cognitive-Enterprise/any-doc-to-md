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
- `.57` rejected 27B test, `qwen/qwen3.6-27b`: the model was present in
  `/models` and could identify all checklist issues, but it failed the
  production latency gate. With `--judge-timeout-s 600`, checklist repeat 1
  passed after `352.59s` load+answer and repeat 2 passed content after
  `215.26s`, exceeding the `120s` steady-answer threshold. A clinical real-PDF
  `c=4 r=1` smoke then failed `0/1` after `514.101s` with repeated LM Studio
  `400 Bad Request` responses on issue `1/12`. Do not use this model for the
  current issue-review judge path without separate runtime/config remediation.
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
- Do not promote `.57` `qwen/qwen3.6-27b`; it failed both latency and real-PDF
  smoke gates in this snapshot.
- Re-run the same real-PDF repeat gate before changing either the model id,
  context window, retry behavior, prompt contract, or LM Studio runtime.

Artifacts from this run were written outside git under:

- `/tmp/adtm-judge-model-selection/`
- `/tmp/adtm-judge-concurrency-matrix/`
- `/tmp/adtm-judge-validation/`
- `/tmp/adtm-judge-validation-concurrent/`
- `/tmp/adtm-judge-retry-validation/`
- `/tmp/adtm-judge-qwen36-27b/`

## Cloud Judge Snapshot, 2026-04-23

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
- OpenAI `gpt-5.1-codex-mini`, using the automatic OpenAI Responses fallback:
  checklist `3/3`, answer mean `11.00s`, max `13.55s`, mean tokens `2877`;
  freeform failed on repeat `1/3` by matching `5/8` gold issues with `3` false
  positives, above the cap of `2`.
- OpenAI `gpt-5.1-codex`, using the automatic OpenAI Responses fallback:
  checklist `3/3`, answer mean `7.09s`, max `7.35s`, mean tokens `2303`;
  freeform failed on repeat `1/3` by matching `5/8` gold issues with `3` false
  positives, above the cap of `2`.
- DeepSeek `deepseek-chat`: checklist `3/3`, answer mean `7.98s`, max `8.18s`,
  mean tokens `1739`; freeform `3/3`, answer mean `28.45s`, max `28.93s`, mean
  tokens `1154`.

OpenAI pricing checked on `2026-04-23` for coding-model experiments:

- `gpt-5.1-codex-mini`: `$0.25/MTok` input, `$2.00/MTok` output
- `gpt-5.1-codex`: `$1.25/MTok` input, `$10.00/MTok` output

Re-check provider pricing before future runs because these prices can change.

Current cloud fallback order:

- Use OpenAI `gpt-4o-mini` as the current measured cloud fallback for the full
  real-PDF issue-review path; it passed both the probe and the real-PDF gate at
  low measured cost.
- Keep Claude `claude-haiku-4-5-20251001` as a viable cloud fallback when
  Anthropic is preferred operationally; it remained reliable at `c=4` after the
  provider-aware 429 backoff path was added.
- Use DeepSeek `deepseek-chat` when DeepSeek is preferred operationally; it
  passed both the probe and the real-PDF gate, but it was materially slower on
  both the freeform phase and the real-PDF issue-review runs.
- Do not promote `gpt-5.1-codex-mini` or `gpt-5.1-codex` as current judge
  defaults for the PDF audit workload. Both reached the OpenAI Responses API
  correctly, but both failed the hidden freeform gate because they produced too
  many false positives on the current prompt contract.

## Cloud Real-PDF Issue-Review Snapshot, 2026-04-23

This snapshot compares Claude Haiku 4.5, OpenAI `gpt-4o-mini`, and DeepSeek
`deepseek-chat` against the current `.57` local default on the same real-PDF
issue-review benchmark cases.

Pricing basis:

- Anthropic pricing checked on `2026-04-22`: Claude Haiku 4.5 standard API is
  listed at `$1/MTok` input and `$5/MTok` output. Re-check provider pricing
  before quoting future cost estimates because prices can change.
- OpenAI pricing checked on `2026-04-23`: `gpt-4o-mini` standard API is listed
  at `$0.15/MTok` input and `$0.60/MTok` output. Re-check provider pricing
  before quoting future cost estimates because prices can change.
- DeepSeek pricing checked on `2026-04-23`: `deepseek-chat` is listed at
  `$0.27/MTok` input for cache misses and `$1.10/MTok` output. Cache-hit input
  pricing is lower, but the benchmark cost helper uses cache-miss pricing for
  one-off benchmark estimates unless a caller supplies different pricing.
- The benchmark now records input and output tokens separately when providers
  expose those usage fields. Cost estimates below use the recorded split token
  usage and do not include any provider dashboard rounding or unrelated usage.
- The Anthropic dashboard reported `$0.54` actual spend for the initial Claude
  real-PDF test batch before split token accounting was added. That batch
  included the `c=4` smoke, the rate-limited pre-backoff `c=4 r=10` clinical
  run, the reliable `c=2 r=3` clinical run, and the `c=2 r=1` three-PDF run.
- The Anthropic dashboard reported an additional `$0.46` actual spend on
  `2026-04-22` for the backoff-enabled `c=4` reruns. The benchmark token-cost
  helper estimated `$0.351625` for the clinical `c=4 r=10` run and `$0.108754`
  for the three-PDF `c=4 r=1` run, which sums to `$0.460379`.

Measured outcome:

- Pre-backoff Claude `claude-haiku-4-5-20251001`, clinical PDF at `c=4`,
  `r=10`: failed rate-limit reliability with `7/10` successful attempts. The
  successful attempts had mean `14.012s`, but repeats 8, 9, and 10 failed with
  Anthropic `429 Too Many Requests` after the per-issue retry budget.
- Backoff-enabled Claude `claude-haiku-4-5-20251001`, clinical PDF at `c=4`,
  `r=10`: passed `10/10`, mean `16.293s`, min `12.699s`, max `23.586s`,
  total tokens `203,005`, input tokens `165,850`, output tokens `37,155`.
  Estimated token cost with prices checked on `2026-04-22`: `$0.351625`.
- Backoff-enabled Claude `claude-haiku-4-5-20251001`, three representative PDFs
  at `c=4`, `r=1`: passed `3/3`, mean `13.607s`, min `13.233s`, max `13.884s`,
  total tokens `62,374`, input tokens `50,779`, output tokens `11,595`.
  Estimated token cost with prices checked on `2026-04-22`: `$0.108754`.
- Earlier Claude `claude-haiku-4-5-20251001`, clinical PDF at `c=2`, `r=3`:
  passed `3/3`, mean `25.715s`, min `24.823s`, max `27.186s`, mean total tokens
  `20,334` per attempt. This remains a conservative fallback if an account's
  rate-limit envelope still cannot sustain `c=4`.
- Earlier Claude `claude-haiku-4-5-20251001`, three representative PDFs at
  `c=2`, `r=1`: passed `3/3`, mean `24.694s`, min `23.949s`, max `25.625s`,
  mean total tokens `20,579` per PDF.
- OpenAI `gpt-4o-mini`, clinical PDF at `c=4`, `r=10`: passed `10/10`, mean
  `11.478s`, min `8.966s`, max `17.092s`, total tokens `164,404`, input tokens
  `144,060`, output tokens `20,344`. Estimated token cost with prices checked
  on `2026-04-22`: `$0.033815`.
- OpenAI `gpt-4o-mini`, three representative PDFs at `c=4`, `r=1`: passed
  `3/3`, mean `10.878s`, min `10.353s`, max `11.563s`, total tokens `50,488`,
  input tokens `44,469`, output tokens `6,019`. Estimated token cost with
  prices checked on `2026-04-23`: `$0.010281`.
- DeepSeek `deepseek-chat`, clinical PDF at `c=4`, `r=3`: passed `3/3`, mean
  `21.726s`, min `21.198s`, max `21.995s`, total tokens `48,636`, input tokens
  `43,098`, output tokens `5,538`. Estimated token cost with prices checked on
  `2026-04-23`: `$0.017728`.
- DeepSeek `deepseek-chat`, three representative PDFs at `c=4`, `r=1`: passed
  `3/3`, mean `23.512s`, min `22.193s`, max `24.646s`, total tokens `50,831`,
  input tokens `44,589`, output tokens `6,242`. Estimated token cost with
  prices checked on `2026-04-23`: `$0.018905`.

Comparison against `.57` local default:

- `.57` `qwen/qwen3-4b-2507`, clinical PDF at `c=4`, `r=10`: passed `10/10`,
  mean `13.828s`, mean total tokens `17,985`.
- `.57` `qwen/qwen3-4b-2507`, three representative PDFs at `c=4`, `r=1`:
  passed `3/3`, mean `14.349s`, mean total tokens `18,058`.
- With 429 backoff, Claude at `c=4` is about `1.18x` slower on the clinical
  repeat than the `.57` local default at `c=4`, and slightly faster on the
  three-PDF representative judge-review mean.
- OpenAI `gpt-4o-mini` at `c=4` was faster than both the `.57` local default and
  Claude on these real-PDF issue-review runs, with lower estimated token spend.
  The local default remains the product default because it preserves offline
  operation and avoids per-call cloud spend.
- DeepSeek `deepseek-chat` at `c=4` was reliable on the measured real-PDF path,
  but slower than both OpenAI `gpt-4o-mini` and Claude on these runs while
  still incurring cloud spend. Its estimated cost remained low, but it does not
  currently beat `gpt-4o-mini` on the combined speed-and-cost tradeoff.

Current recommendation:

- Keep `.57` `qwen/qwen3-4b-2507` at `c=4` as the practical default when local
  hardware is available.
- Use OpenAI `gpt-4o-mini` at `c=4` as the measured low-cost cloud fallback for
  this real-PDF issue-review path when local hardware is unavailable.
- Keep Claude `claude-haiku-4-5-20251001` at `c=4` as a measured cloud fallback
  when Claude is operationally preferred, provided the 429 backoff path is
  available. Use `c=2` if an Anthropic account still cannot sustain the `c=4`
  token/request burst.
- Use DeepSeek `deepseek-chat` at `c=4` only when DeepSeek is preferred
  operationally; the measured path was reliable, but slower than the current
  OpenAI fallback on this workload.
- Keep using provider billing data as the final cost source. The benchmark's
  split token accounting is suitable for per-run estimates and model
  comparison, but provider invoices may include rounding, caching, or unrelated
  account usage.
- Use `python -m anydoc2md.judge_benchmark_cost_report <benchmark.json>` to
  generate an auditable dated cost estimate from benchmark JSON. For providers
  or models without built-in prices, pass explicit prices plus `--priced-at` and
  `--price-source-url`.

Cloud probe artifacts from this run were written outside git under:

- `/tmp/adtm-cloud-judge-probes/`
- `/tmp/adtm-cloud-realpdf-benchmark/`
