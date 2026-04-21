"""
CLI helper: find a local model that can do ADTM judge work (audit prompt).

This probes an OpenAI-compatible endpoint (e.g. LM Studio) by:
1) Fetching model ids from GET <judge_url>/models
2) Sorting by a best-effort size hint parsed from the model id string
3) Running a fixed synthetic audit test case against each model
4) Reporting the fastest passing models (top 10 by default)

Usage:
  python -m anydoc2md.find_judge --judge-url http://127.0.0.1:1234/v1 --show-all
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from anydoc2md.judge_probe_case import REQUIRED_MARKERS, build_probe_case
from anydoc2md.judge_probe_models import ModelInfo, fetch_model_ids, parse_size_hint_billions
from anydoc2md.judge_probe_runner import ProbeResult, probe_one_model
from anydoc2md.settings import DEFAULT_JUDGE_TIMEOUT_S, ENV_JUDGE_TIMEOUT_S

_SLOW_JUDGE_TIMEOUT_MULTIPLIER = 4
_DEFAULT_PROBE_JUDGE_TIMEOUT_S = DEFAULT_JUDGE_TIMEOUT_S * _SLOW_JUDGE_TIMEOUT_MULTIPLIER


def _env_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _format_size(size_hint_b: float | None) -> str:
    if size_hint_b is None:
        return "?"
    if size_hint_b.is_integer():
        return f"{int(size_hint_b)}B"
    return f"{size_hint_b:g}B"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe an OpenAI-compatible judge endpoint to find the smallest/fastest "
            "model that can reliably surface issues on a synthetic ADTM audit case."
        )
    )
    parser.add_argument(
        "--judge-url",
        required=True,
        help='Base URL for OpenAI-compatible endpoint, e.g. "http://127.0.0.1:1234/v1".',
    )
    parser.add_argument(
        "--judge-timeout-s",
        type=int,
        default=None,
        metavar="SECS",
        help=(
            f"HTTP read timeout for judge calls (default: {_DEFAULT_PROBE_JUDGE_TIMEOUT_S} "
            f"unless {ENV_JUDGE_TIMEOUT_S} is set)."
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        metavar="N",
        help="How many fastest passing models to print (default: 10).",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print all model probe results, not just the fastest passing ones.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    env_timeout = _env_int(ENV_JUDGE_TIMEOUT_S)
    judge_timeout_s = (
        args.judge_timeout_s
        if args.judge_timeout_s is not None
        else (env_timeout if env_timeout is not None else _DEFAULT_PROBE_JUDGE_TIMEOUT_S)
    )
    if judge_timeout_s <= 0:
        print("Error: judge timeout must be > 0.", flush=True)
        return 2

    try:
        model_ids = fetch_model_ids(args.judge_url)
    except Exception as exc:
        print(f"Error: unable to fetch models from {args.judge_url!r}: {exc}", flush=True)
        return 2

    if not model_ids:
        print(f"Error: no models returned by {args.judge_url.rstrip('/')}/models", flush=True)
        return 2

    models = [
        ModelInfo(model_id=model_id, size_hint_b=parse_size_hint_billions(model_id))
        for model_id in model_ids
    ]
    models.sort(key=lambda m: (m.size_hint_b is None, m.size_hint_b or 0.0, m.model_id))

    with tempfile.TemporaryDirectory(prefix="anydoc2md-find-judge-") as tmp:
        probe_case = build_probe_case(Path(tmp))
        results: list[ProbeResult] = []
        for model in models:
            results.append(
                probe_one_model(
                    model=model,
                    judge_url=args.judge_url,
                    judge_timeout_s=judge_timeout_s,
                    probe_case=probe_case,
                )
            )

    passing = [r for r in results if r.passed]
    passing.sort(key=lambda r: (r.latency_s, r.model_id))

    print(f"Judge URL: {args.judge_url}")
    print(f"Models discovered: {len(models)}")
    print(f"Models passing: {len(passing)}")
    print(f"Probe judge timeout: {judge_timeout_s}s")
    print(f"Required markers: {', '.join(REQUIRED_MARKERS)}")
    print("")

    if not passing:
        print("No models passed the synthetic audit probe.", flush=True)
        if not args.show_all:
            print("Tip: re-run with --show-all to see per-model failure reasons.", flush=True)
            return 1
        print("")

    if passing:
        print(f"Fastest passing models (top {args.top_n}):")
        for index, result in enumerate(passing[: max(1, args.top_n)], start=1):
            print(
                f"{index:>2}. {result.model_id} | size={_format_size(result.size_hint_b)} "
                f"| {result.latency_s:.2f}s | tokens={result.tokens_used} "
                f"| violations={result.violations_count} | confidence={result.confidence}"
            )

    if args.show_all:
        print("")
        print("All results (size-sorted probe order):")
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            reason = "" if result.passed else f" | {result.reason}"
            print(
                f"{status} {result.model_id} | size={_format_size(result.size_hint_b)} "
                f"| {result.latency_s:.2f}s | tokens={result.tokens_used} "
                f"| violations={result.violations_count} | confidence={result.confidence}"
                f"{reason}"
            )

    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())

