"""CLI for PDF judge concurrency benchmarking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from anydoc2md.judge_pdf_concurrency_benchmark_core import (
    parse_case_spec,
    parse_concurrency_levels,
    run_benchmark_matrix,
)
from anydoc2md.settings import DEFAULT_JUDGE_TIMEOUT_S, JudgeSettings

_DEFAULT_CONCURRENCY_LEVELS = (1, 2, 4, 8)
_SLOW_JUDGE_TIMEOUT_MULTIPLIER = 4
_DEFAULT_TIMEOUT_S = DEFAULT_JUDGE_TIMEOUT_S * _SLOW_JUDGE_TIMEOUT_MULTIPLIER


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a PDF issue-review concurrency matrix against an OpenAI-compatible "
            "judge endpoint using explicit source/audit-PDF cases."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        metavar="SOURCE::AUDIT_PDF[::CANDIDATE]",
        help="Benchmark case. Repeat this flag to include multiple PDFs.",
    )
    parser.add_argument("--judge-url", required=True, help="OpenAI-compatible base URL.")
    parser.add_argument("--judge-model", required=True, help="Judge model id.")
    parser.add_argument(
        "--judge-timeout-s",
        type=int,
        default=_DEFAULT_TIMEOUT_S,
        metavar="SECS",
        help=f"HTTP read timeout per judge call (default: {_DEFAULT_TIMEOUT_S}).",
    )
    parser.add_argument(
        "--concurrency-levels",
        default=",".join(str(level) for level in _DEFAULT_CONCURRENCY_LEVELS),
        metavar="CSV",
        help="Comma-separated PDF judge concurrency levels (default: 1,2,4,8).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        metavar="N",
        help="Repeats per case/concurrency level (default: 1).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path for machine-readable benchmark output. Prefer a gitignored or /tmp path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        cases = [parse_case_spec(spec) for spec in args.case]
        concurrency_levels = parse_concurrency_levels(args.concurrency_levels)
        if args.repeats < 1:
            raise ValueError("repeats must be positive")
        if args.judge_timeout_s < 1:
            raise ValueError("judge timeout must be positive")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    settings = JudgeSettings(
        url=args.judge_url,
        model=args.judge_model,
        timeout_s=args.judge_timeout_s,
    )
    print(f"Cases: {len(cases)}", flush=True)
    print(f"Concurrency levels: {', '.join(str(level) for level in concurrency_levels)}", flush=True)
    print(f"Repeats: {args.repeats}", flush=True)
    print(f"Judge: {settings.url} model={settings.model}", flush=True)

    started = time.monotonic()
    try:
        result = run_benchmark_matrix(
            cases=cases,
            concurrency_levels=concurrency_levels,
            repeats=args.repeats,
            base_settings=settings,
        )
    except Exception as exc:
        print(f"Error: benchmark failed: {exc}", file=sys.stderr)
        return 1

    result["total_elapsed_s"] = round(time.monotonic() - started, 3)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print_summary(result)
    print(f"Wrote: {args.output_json}", flush=True)
    return 0 if all(attempt["succeeded"] for attempt in result["attempts"]) else 1


def _print_summary(result: dict[str, Any]) -> None:
    print("Summary:", flush=True)
    for row in result["summary"]:
        print(
            "  "
            f"concurrency={row['concurrency']} "
            f"success={row['success_count']}/{row['attempt_count']} "
            f"mean_elapsed_s={row['mean_elapsed_s']} "
            f"max_active_calls={row['max_active_calls']}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
