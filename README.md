# any-doc-to-md

`anydoc2md` is a shared Python package for:

- document-to-Markdown conversion
- structural and fidelity QA over conversion outputs
- multi-adapter converter tournaments
- near-tie LLM judging between competing Markdown outputs

Source lives under `src/anydoc2md/`.

## Scope

This package owns reusable conversion and judging logic.

This package does not own:

- host-application `.env` loading
- process exit behavior
- PRAI-specific orchestration outside the shared conversion/judge surfaces

Host applications are expected to provide runtime configuration through environment variables or explicit `JudgeSettings`.

## Judge Configuration

The near-tie judge is configured via `anydoc2md.settings`.

Required environment variables:

- `ANYDOC2MD_JUDGE_URL`
- `ANYDOC2MD_JUDGE_MODEL`

Optional environment variables:

- `ANYDOC2MD_JUDGE_TIMEOUT_S`
- `ANYDOC2MD_JUDGE_MAX_TOKENS`
- `ANYDOC2MD_JUDGE_DISABLE_THINKING`
- `ANYDOC2MD_JUDGE_TEMPERATURE`

If required values are missing, the library raises `AnyDocToMdConfigError` when loading settings explicitly, or returns an error verdict when `judge_near_tie()` attempts to load them implicitly.

## Example

```python
from anydoc2md.llm_judge import judge_near_tie
from anydoc2md.settings import JudgeSettings

settings = JudgeSettings(
    url="http://127.0.0.1:1234/v1",
    model="qwen/qwen3.6-35b-a3b",
)

verdict = judge_near_tie(candidates, source_path, traits, settings=settings)
```

## Development

The package is a normal `src/` layout project:

```bash
cd packages/any-doc-to-md
python -m pip install -e .
```

Within PRAI, the backend keeps this submodule importable through `backend/sitecustomize.py` for the usual `cd backend && PYTHONPATH=. ...` workflow.
