# ADTM LLM Judge Setup

Review date: 2026-04-24.

ADTM can run without an LLM judge. The default public smoke path uses
`audit_mode="light"`, runs the `inhouse` adapter, and spends no cloud API
credits. The LLM judge is used only when a host chooses `audit_mode="auto"` and
provides judge settings.

The judge is a model endpoint, not a coding-agent product. Tools such as Codex,
Claude Code, or OpenHands can help maintain ADTM or write project-local
remediation hooks, but the runtime judge path calls configured model APIs
through `anydoc2md.settings.JudgeSettings`.

## When To Use A Judge

Use `audit_mode="light"` when you need a fast, local, cost-free conversion and
are willing to accept the score-selected candidate without source-fidelity LLM
review.

Use `audit_mode="auto"` when PDF source fidelity matters enough to justify the
extra latency and, for cloud providers, possible API cost. In `auto` mode, ADTM
falls back to light mode when judge settings are absent.

For PDFs, ADTM first renders the winning Markdown to an audit PDF and runs
deterministic suspect localization. The LLM sees only bounded issue-review
packets when suspicious windows are found; it is not asked to re-read the whole
document blindly.

## Required Environment Variables

Common variables:

```bash
export ANYDOC2MD_JUDGE_PROVIDER="lm_studio"  # lm_studio, openai, deepseek, claude
export ANYDOC2MD_JUDGE_MODEL="model-id"
export ANYDOC2MD_JUDGE_TIMEOUT_S="240"
export ANYDOC2MD_JUDGE_MAX_TOKENS="4096"
export ANYDOC2MD_JUDGE_PDF_CONCURRENCY="4"
```

Provider-specific variables:

```bash
# Required for lm_studio.
export ANYDOC2MD_JUDGE_URL="http://127.0.0.1:1234/v1"

# Required only for cloud providers.
export OPENAI_API_KEY="..."
export DEEPSEEK_API_KEY="..."
export CLAUDE_API_KEY="..."
```

Cloud provider defaults are built in:

| Provider | Default URL | API key variable |
|---|---|---|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `deepseek` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| `claude` | `https://api.anthropic.com/v1/messages` | `CLAUDE_API_KEY` |

OpenAI models that reject `/v1/chat/completions` are retried through
`/v1/responses` automatically by the judge client.

## Local LM Studio Setup

Start LM Studio with an OpenAI-compatible server, load the chosen model, then
configure ADTM:

```bash
export ANYDOC2MD_JUDGE_PROVIDER="lm_studio"
export ANYDOC2MD_JUDGE_URL="http://127.0.0.1:1234/v1"
export ANYDOC2MD_JUDGE_MODEL="qwen/qwen3-4b-2507"
export ANYDOC2MD_JUDGE_TIMEOUT_S="240"
export ANYDOC2MD_JUDGE_PDF_CONCURRENCY="4"
```

List models exposed by the endpoint:

```bash
cd packages/any-doc-to-md
PYTHONPATH=src python -m anydoc2md.find_judge \
  --judge-url "$ANYDOC2MD_JUDGE_URL" \
  --list-models-only
```

Probe one model:

```bash
PYTHONPATH=src python -m anydoc2md.find_judge \
  --judge-url "$ANYDOC2MD_JUDGE_URL" \
  --model-name "$ANYDOC2MD_JUDGE_MODEL" \
  --repeats 3 \
  --timeout-s 120 \
  --judge-timeout-s 240 \
  --show-all
```

Current local recommendation from the 2026-04-22 snapshot:

| Role | Model | Concurrency | Notes |
|---|---|---:|---|
| Practical local default | `.57` `qwen/qwen3-4b-2507` | `4` | Passed repeated real-PDF issue-review gates with retry enabled. |
| Conservative local fallback | `.57` `qwen/qwen3-30b-a3b-2507` | `4` | Passed the same path but was roughly three times slower on measured runs. |
| Constrained-GPU fallback | `.59` `qwen3-4b-instruct-2507` | `2` | Passed on weaker GPU hardware with lower concurrency. |
| Do not promote | `.57` `qwen/qwen3.6-27b` | n/a | Passed checklist content but failed production latency and real-PDF smoke gates. |

Re-run the same gates when model id, runtime, context window, prompt contract,
parser behavior, hardware, or concurrency changes.

## Cloud Provider Setup

Cloud providers are optional fallbacks. They can be faster or operationally
convenient, but they may spend API credits. Provider dashboards and invoices are
the final billing source.

OpenAI:

```bash
export OPENAI_API_KEY="..."
PYTHONPATH=src python -m anydoc2md.find_judge --judge-provider openai --list-models-only
PYTHONPATH=src python -m anydoc2md.find_judge \
  --judge-provider openai \
  --model-name gpt-4o-mini \
  --repeats 3 \
  --timeout-s 120 \
  --judge-timeout-s 240 \
  --show-all
```

DeepSeek:

```bash
export DEEPSEEK_API_KEY="..."
PYTHONPATH=src python -m anydoc2md.find_judge --judge-provider deepseek --list-models-only
PYTHONPATH=src python -m anydoc2md.find_judge \
  --judge-provider deepseek \
  --model-name deepseek-chat \
  --repeats 3 \
  --timeout-s 120 \
  --judge-timeout-s 240 \
  --show-all
```

Claude:

```bash
export CLAUDE_API_KEY="..."
PYTHONPATH=src python -m anydoc2md.find_judge --judge-provider claude --list-models-only
PYTHONPATH=src python -m anydoc2md.find_judge \
  --judge-provider claude \
  --model-name claude-haiku-4-5-20251001 \
  --repeats 3 \
  --timeout-s 120 \
  --judge-timeout-s 240 \
  --show-all
```

Current cloud fallback roles from the 2026-04-23 snapshot:

| Role | Provider/model | Notes |
|---|---|---|
| Low-cost cloud fallback | OpenAI `gpt-4o-mini` | Passed probes and real-PDF gate with low estimated token cost. |
| Fast-premium OpenAI fallback | OpenAI `gpt-5.4-mini` | Fastest measured cloud judge, materially higher standard-list estimated cost. |
| Anthropic-preferred fallback | Claude `claude-haiku-4-5-20251001` | Reliable at `c=4` after provider-aware 429 backoff; use `c=2` for stricter rate-limit envelopes. |
| DeepSeek-preferred fallback | DeepSeek `deepseek-chat` | Reliable but slower than the current OpenAI fallback on measured real-PDF runs. |
| Do not promote for current prompt | OpenAI `gpt-4.1-mini`, `gpt-5-mini`, `o3-mini`, `o4-mini`, `gpt-5.1-codex-mini`, `gpt-5.1-codex` | Failed hidden freeform quality gates or lost the measured speed/cost tradeoff. |

## Cost Warnings

Prices and free allowances can change. Always record the date, provider, model,
input/output token counts, pricing source, and whether provider dashboard costs
matched the benchmark estimate.

Built-in price checks currently used by ADTM cost reports:

| Provider/model | Input price | Output price | Price checked |
|---|---:|---:|---|
| Claude `claude-haiku-4-5*` | `$1.00/MTok` | `$5.00/MTok` | `2026-04-22` |
| OpenAI `gpt-4o-mini` | `$0.15/MTok` | `$0.60/MTok` | `2026-04-23` |
| OpenAI `gpt-5.4-mini` | `$0.75/MTok` | `$4.50/MTok` | `2026-04-23` |
| OpenAI `o4-mini` | `$1.10/MTok` | `$4.40/MTok` | `2026-04-23` |
| DeepSeek `deepseek-chat` | `$0.27/MTok` cache miss | `$1.10/MTok` | `2026-04-23` |

If your account has a free-token allowance, the provider may bill less than the
standard-list estimate. Keep list-price estimates in benchmark docs for
provider-neutral comparison, and use provider billing data as the final record
of actual spend.

## Real-PDF Concurrency Benchmark

After a model passes `find_judge`, measure real-PDF issue-review concurrency on
explicit source/candidate cases:

```bash
PYTHONPATH=src python -m anydoc2md.judge_pdf_concurrency_benchmark \
  --judge-provider openai \
  --judge-model gpt-4o-mini \
  --judge-timeout-s 240 \
  --concurrency-levels 1,2,4 \
  --case /path/to/source.pdf::/path/to/winner/audit_candidate.pdf::inhouse \
  --output-json /tmp/adtm-judge-concurrency/openai-gpt4o-mini.json
```

Use gitignored or `/tmp` output paths. Do not commit benchmark JSON artifacts
unless a release process explicitly asks for a curated fixture or summary.

Estimate benchmark cost from the JSON artifact:

```bash
PYTHONPATH=src python -m anydoc2md.judge_benchmark_cost_report \
  /tmp/adtm-judge-concurrency/openai-gpt4o-mini.json \
  --output-json /tmp/adtm-judge-concurrency/openai-gpt4o-mini-cost.json
```

For models without built-in pricing, provide explicit dated pricing:

```bash
PYTHONPATH=src python -m anydoc2md.judge_benchmark_cost_report \
  /tmp/adtm-judge-concurrency/custom-model.json \
  --provider openai \
  --model custom-model-id \
  --input-price-per-mtok 0.15 \
  --output-price-per-mtok 0.60 \
  --priced-at 2026-04-24 \
  --price-source-url https://example.invalid/pricing
```

## Production Defaults

Keep `ANYDOC2MD_JUDGE_PDF_CONCURRENCY=4` only after the endpoint passes the
real-PDF concurrency gate. Lower it to `1` or `2` for constrained local
hardware, strict cloud rate limits, or new models that have not been measured.

Keep `ANYDOC2MD_JUDGE_DISABLE_THINKING=true` unless you are deliberately
testing a model/runtime that needs different reasoning controls. Some providers
reject unsupported temperature or token parameters; ADTM already handles known
OpenAI Responses fallback constraints.

Do not make cloud providers the product default for offline-first deployments.
The local judge path preserves offline operation and avoids per-call provider
cost.

## Related Docs

- Judge benchmark snapshot:
  [`specs/local-llm-benchmark.md`](specs/local-llm-benchmark.md)
- Cost report helper:
  `python -m anydoc2md.judge_benchmark_cost_report`
- Runtime settings source:
  `src/anydoc2md/settings.py`
