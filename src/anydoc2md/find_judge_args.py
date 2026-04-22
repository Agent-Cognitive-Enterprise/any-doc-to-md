"""Argument parsing for the find_judge CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from anydoc2md.judge_probe_case import DEFAULT_PASS_THRESHOLD
from anydoc2md.settings import (
    DEFAULT_JUDGE_PROVIDER,
    DEFAULT_JUDGE_TIMEOUT_S,
    ENV_JUDGE_PROVIDER,
    ENV_JUDGE_TIMEOUT_S,
)

SLOW_JUDGE_TIMEOUT_MULTIPLIER = 4
DEFAULT_PROBE_JUDGE_TIMEOUT_S = DEFAULT_JUDGE_TIMEOUT_S * SLOW_JUDGE_TIMEOUT_MULTIPLIER


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe a judge provider endpoint to find the smallest/fastest "
            "model that can reliably surface issues on a fixture-backed ADTM audit case."
        )
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help=(
            "Keep the synthetic probe-case PDFs/Markdown on disk and print their path "
            "(by default they are created in a temp dir and deleted)."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Directory where a per-run artifacts subdirectory will be created and preserved. "
            "This implies --keep-artifacts."
        ),
    )
    parser.add_argument(
        "--judge-url",
        default=None,
        help=(
            'Base URL for the judge endpoint, e.g. "http://127.0.0.1:1234/v1". '
            "Required for lm_studio; cloud providers have defaults."
        ),
    )
    parser.add_argument(
        "--judge-provider",
        default=None,
        help=(
            "Judge provider: lm_studio, openai, deepseek, or claude "
            f"(default: {ENV_JUDGE_PROVIDER} or {DEFAULT_JUDGE_PROVIDER})."
        ),
    )
    parser.add_argument(
        "--judge-timeout-s",
        type=int,
        default=None,
        metavar="SECS",
        help=(
            f"HTTP read timeout for judge calls (default: {DEFAULT_PROBE_JUDGE_TIMEOUT_S} "
            f"unless {ENV_JUDGE_TIMEOUT_S} is set)."
        ),
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        metavar="SECS",
        help=(
            "Maximum acceptable steady answer time in seconds (default: 30). "
            "Repeat 1 is treated as load+answer and excluded when repeats > 1."
        ),
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=10,
        metavar="N",
        help="How many times to test each selected model (default: 10).",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=DEFAULT_PASS_THRESHOLD,
        metavar="FRACTION",
        help=(
            "Minimum fraction of expected checklist issues required to pass "
            f"(default: {DEFAULT_PASS_THRESHOLD:g})."
        ),
    )
    parser.add_argument(
        "--model-name",
        action="append",
        default=[],
        metavar="MODEL",
        help="Probe only the specified model id. Repeat this flag for multiple exact ids.",
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
    parser.add_argument(
        "--show-errors",
        action="store_true",
        help="Show diagnostic failure/error reasons in probe output.",
    )
    parser.add_argument(
        "--list-models-only",
        action="store_true",
        help="Fetch and print model ids, then exit without running paid probes.",
    )
    parser.add_argument(
        "--phase2-only",
        action="store_true",
        help="Skip checklist shortlisting and run only phase 2 on the selected models.",
    )
    stop_group = parser.add_mutually_exclusive_group()
    stop_group.add_argument(
        "--stop-on-fail",
        dest="stop_on_fail",
        action="store_true",
        default=True,
        help="Stop testing a model after its first failed repeat (default).",
    )
    stop_group.add_argument(
        "--no-stop-on-fail",
        dest="stop_on_fail",
        action="store_false",
        help="Run every repeat for every selected model, even after failures.",
    )
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument(
        "--color",
        action="store_true",
        help="Force ANSI color output for PASS/FAIL.",
    )
    color_group.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )
    return parser
