# ADTM Agent Conversion Guide

This document is the instructions for a coding agent performing document
conversion with ADTM. Follow this sequence exactly.

## When to use this guide

Use this guide when tasked with converting a document and ensuring the output
quality is acceptable. The guide assumes a judge is configured via environment
variables. Without a judge, ADTM runs in light mode and produces no findings —
the output is accepted as-is.

## The sequence

### Step 1 — convert

```bash
anydoc2md convert <source_file> --output-dir <output_dir> \
    --project-dir <project_dir> --audit-mode auto
```

`--project-dir` is the root of the host project (the directory that contains
your `.any-doc-to-md/` folder). Defaults to the current working directory when
omitted. Use the same `--project-dir` for every document in a project so all
findings and scaffolds are written to one location.

Each output directory holds exactly one conversion result. Use a separate
directory per source document — re-running to the same path overwrites
`index.md`, `images/`, and `anydoc2md-result.json`.

This produces:
- `<output_dir>/index.md` — the converted Markdown
- `<output_dir>/images/` — extracted images referenced from `index.md` (present
  only when the source document contains images that were successfully extracted)
- `<output_dir>/anydoc2md-result.json` — full tournament result including any
  judge findings
- `<project_dir>/.any-doc-to-md/llm-findings/<source_filename>.json` — judge
  verdict and remediation plan (only when findings exist)
- `<project_dir>/.any-doc-to-md/qa-extensions/<source_filename>.py` — QA check
  scaffolds (only when findings exist)
- `<project_dir>/.any-doc-to-md/inhouse-extensions/<source_filename>.py` —
  converter fix scaffolds (only when findings exist)

### Step 2 — check the result

Read `<output_dir>/anydoc2md-result.json`. Check:

```json
{
  "judge_verdict": { "violations": [...] },
  "escalated": false
}
```

- If `violations` is empty or `judge_verdict` is null → output is accepted.
  Stop here.
- If `violations` contains `"severity": "major"` or `"severity": "critical"`
  entries → proceed to step 3.
- If `escalated` is true → all candidates were exhausted. Proceed to step 3
  and treat attempt count as already at the limit.

### Step 3 — read the scaffolds

Open the scaffold files written under `<project_dir>/.any-doc-to-md/`:

**`qa-extensions/<source_filename>.py`**

Each stub function has comments explaining the violation type, evidence, and
root cause. For violation types that map to existing ADTM checks, the check
function is already wired. For unknown types, a TODO stub is generated.

Your job:
- For TODO stubs: implement the check body so it returns `CheckResult` with
  `status="fail"` when the issue is present, `status="pass"` otherwise.
- Do not remove or disable existing checks.
- Keep each check body small and deterministic.

**`inhouse-extensions/<source_filename>.py`**

The `apply_inhouse_extension(source_path, staging_dir, converter_name)` function
patches `staging_dir/index.md` after the inhouse converter runs.

Your job:
- For TODO stubs: read the embedded evidence and implement a targeted fix.
- The fix must be deterministic — no LLM calls inside this function.
- Read and write only `staging_dir/index.md` (and `staging_dir/images/` if
  needed). Do not touch source files.
- Keep the fix minimal and specific to the reported issue class.

### Step 4 — re-run

```bash
anydoc2md convert <source_file> --output-dir <output_dir> --audit-mode auto
```

ADTM picks up the implemented scaffolds automatically from `.any-doc-to-md/`.

### Step 5 — repeat up to 3 attempts total

If major findings persist after the re-run, return to step 3 with the updated
scaffolds (overwrite=True is used on re-runs so your implementations are
preserved and can be refined).

**Hard limit: 3 conversion attempts total** (counting step 1).

### Step 6 — escalate if still failing

If major findings persist after 3 attempts, stop and report to a human with:

- The `anydoc2md-result.json` from the last run
- The `<project_dir>/.any-doc-to-md/llm-findings/<source_filename>.json` file
- A short description of what was attempted and what changed in each scaffold
  version
- The source file and the last `index.md` output

Do not attempt a fourth retry. Some documents have structural issues that
require converter-level changes or human judgment, not scaffold patches.

## Rules

1. Never implement a scaffold without reading the evidence comments first.
2. Never skip the re-run step after implementing a scaffold.
3. Never disable a QA check to make a run pass.
4. Never call an LLM inside `apply_inhouse_extension`.
5. If a fix cannot be made deterministic, say so and escalate.
6. Keep scaffold implementations small — one violation type, one targeted change.

## Checking judge configuration

If `judge_verdict` is always null, the judge is not configured. Set:

```bash
export ANYDOC2MD_JUDGE_PROVIDER=lm_studio       # or openai, deepseek, claude
export ANYDOC2MD_JUDGE_URL=http://127.0.0.1:1234/v1
export ANYDOC2MD_JUDGE_MODEL=<model-id>
```

See [`docs/llm-judge-setup.md`](llm-judge-setup.md) for provider setup and
[`docs/find_judge`](../src/anydoc2md/find_judge.py) for model selection.
