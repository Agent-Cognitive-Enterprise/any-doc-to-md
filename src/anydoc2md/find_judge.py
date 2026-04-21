"""
CLI helper: find a local model that can do ADTM judge work (audit prompt).

This probes an OpenAI-compatible endpoint (e.g. LM Studio) by:
1) Fetching model ids from GET <judge_url>/models
2) Sorting by a best-effort size hint parsed from the model id string
3) Running a fixed fixture-backed audit test case against each model
4) Reporting the fastest passing models (top 10 by default)

"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

from anydoc2md.judge_probe_case import EXPECTED_ISSUE_CLASSES, ProbeCase, build_probe_case
from anydoc2md.find_judge_report import (
    _color_conclusion_line,
    _color_status,
    _format_duration,
    _format_load_est,
    _format_size,
    _render_attempt_status,
    _render_model_conclusion,
    _render_progress,
    _summarize_model,
)
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


def _select_models(all_model_ids: list[str], requested_model_names: list[str]) -> list[str]:
    if not requested_model_names:
        return all_model_ids

    requested = [name.strip() for name in requested_model_names if name.strip()]
    requested_set = set(requested)
    available_set = set(all_model_ids)
    missing = [name for name in requested if name not in available_set]
    if missing:
        missing_joined = ", ".join(missing)
        raise ValueError(f"Requested model(s) not found on endpoint: {missing_joined}")

    return [model_id for model_id in all_model_ids if model_id in requested_set]


@contextmanager
def _probe_case_context(
    *,
    keep_artifacts: bool,
    artifacts_dir: Path | None,
) -> Iterator[tuple[ProbeCase, Path | None]]:
    if keep_artifacts:
        if artifacts_dir is not None:
            root = artifacts_dir.expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            probe_case_dir = Path(tempfile.mkdtemp(prefix="anydoc2md-find-judge-", dir=root))
        else:
            probe_case_dir = Path(tempfile.mkdtemp(prefix="anydoc2md-find-judge-"))
        yield build_probe_case(probe_case_dir), probe_case_dir
        return

    with tempfile.TemporaryDirectory(prefix="anydoc2md-find-judge-") as tmp:
        yield build_probe_case(Path(tmp)), None


def _print_artifact_paths(probe_case: ProbeCase, probe_case_dir: Path | None) -> None:
    if probe_case_dir is None:
        return
    print(f"Artifacts kept at: {probe_case_dir}", flush=True)
    print(f"  source:    {probe_case.source_pdf}", flush=True)
    print(f"  candidate: {probe_case.candidate_pdf}", flush=True)
    print(f"  staging:   {probe_case.candidate.staging_dir}", flush=True)
    print("", flush=True)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe an OpenAI-compatible judge endpoint to find the smallest/fastest "
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
        "--model-name",
        action="append",
        default=[],
        metavar="MODEL",
        help=(
            "Probe only the specified model id. Repeat this flag to probe multiple exact model ids."
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


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    env_timeout = _env_int(ENV_JUDGE_TIMEOUT_S)
    judge_timeout_s = (
        args.judge_timeout_s
        if args.judge_timeout_s is not None
        else (env_timeout if env_timeout is not None else _DEFAULT_PROBE_JUDGE_TIMEOUT_S)
    )
    repeats = args.repeats
    answer_timeout_s = args.timeout_s
    color_enabled = args.color or (not args.no_color and sys.stdout.isatty())
    if judge_timeout_s <= 0:
        print("Error: judge timeout must be > 0.", flush=True)
        return 2
    if answer_timeout_s <= 0:
        print("Error: timeout-s must be > 0.", flush=True)
        return 2
    if repeats <= 0:
        print("Error: repeats must be > 0.", flush=True)
        return 2

    print(f"Fetching models from: {args.judge_url.rstrip('/')}/models", flush=True)
    try:
        model_ids = fetch_model_ids(args.judge_url)
    except Exception as exc:
        print(f"Error: unable to fetch models from {args.judge_url!r}: {exc}", flush=True)
        return 2

    if not model_ids:
        print(f"Error: no models returned by {args.judge_url.rstrip('/')}/models", flush=True)
        return 2

    try:
        selected_model_ids = _select_models(model_ids, args.model_name)
    except ValueError as exc:
        print(f"Error: {exc}", flush=True)
        return 2

    if not selected_model_ids:
        print("Error: no models selected for probing.", flush=True)
        return 2

    print(f"Models discovered: {len(model_ids)}", flush=True)
    print(f"Models selected: {len(selected_model_ids)}", flush=True)
    print("Sorting by best-effort size hint (parsed from model id)...", flush=True)
    models = [
        ModelInfo(model_id=model_id, size_hint_b=parse_size_hint_billions(model_id))
        for model_id in selected_model_ids
    ]
    models.sort(key=lambda m: (m.size_hint_b is None, m.size_hint_b or 0.0, m.model_id))
    print(f"Probe judge timeout: {judge_timeout_s}s", flush=True)
    print(f"Production answer timeout: {answer_timeout_s:g}s", flush=True)
    print(f"Repeats per model: {repeats}", flush=True)

    results: list[ProbeResult] = []
    keep_artifacts = bool(args.keep_artifacts or args.artifacts_dir)
    total_attempts = len(models) * repeats
    run_started_at = time.monotonic()

    with _probe_case_context(
        keep_artifacts=keep_artifacts,
        artifacts_dir=args.artifacts_dir,
    ) as (probe_case, probe_case_dir):
        _print_artifact_paths(probe_case, probe_case_dir)
        completed_attempts = 0
        for model_index, model in enumerate(models, start=1):
            model_attempt_results: list[ProbeResult] = []
            for repeat_index in range(1, repeats + 1):
                prefix = (
                    f"{_render_progress(completed_attempts, total_attempts)} "
                    f"model {model_index}/{len(models)} repeat {repeat_index}/{repeats} "
                    f"{'load+answer' if repeat_index == 1 else 'answer'} "
                    f"{model.model_id} (size={_format_size(model.size_hint_b)})..."
                )
                print(prefix, end="", flush=True)
                result = probe_one_model(
                    model=model,
                    judge_url=args.judge_url,
                    judge_timeout_s=judge_timeout_s,
                    probe_case=probe_case,
                )
                completed_attempts += 1
                elapsed_s = time.monotonic() - run_started_at
                mean_attempt_s = elapsed_s / max(1, completed_attempts)
                remaining_attempts = total_attempts - completed_attempts
                eta_s = mean_attempt_s * remaining_attempts
                status = "PASS" if result.passed else "FAIL"
                answer_timed_out = (
                    result.latency_s > answer_timeout_s
                    and (repeat_index > 1 or repeats == 1)
                )
                speed_note = f" | answer>{answer_timeout_s:g}s" if answer_timed_out else ""
                reason = "" if result.passed else f" | {result.reason}"
                print(
                    f"\r{_render_attempt_status(completed_attempts, total_attempts, elapsed_s=elapsed_s, eta_s=eta_s, status=status, color_enabled=color_enabled)} "
                    f"{model.model_id} | repeat {repeat_index}/{repeats} "
                    f"| {'load+answer' if repeat_index == 1 else 'answer'} "
                    f"| {result.latency_s:.2f}s | tokens={result.tokens_used} "
                    f"| violations={result.violations_count} | confidence={result.confidence} "
                    f"{speed_note}{reason}",
                    flush=True,
                )
                results.append(result)
                model_attempt_results.append(result)
            summary = _summarize_model(
                model,
                model_attempt_results,
                answer_timeout_s=answer_timeout_s,
            )
            print(
                _color_conclusion_line(
                    _render_model_conclusion(summary),
                    passed=summary.passed,
                    enabled=color_enabled,
                ),
                flush=True,
            )

    summaries = [
        _summarize_model(
            model,
            [result for result in results if result.model_id == model.model_id],
            answer_timeout_s=answer_timeout_s,
        )
        for model in models
    ]
    passing = [summary for summary in summaries if summary.passed]
    passing.sort(key=lambda summary: (summary.mean_answer_latency_s, summary.model_id))
    total_elapsed_s = time.monotonic() - run_started_at

    print(f"Judge URL: {args.judge_url}")
    print(f"Models discovered: {len(model_ids)}")
    print(f"Models selected: {len(models)}")
    print(f"Models passing all repeats: {len(passing)}")
    print(f"Probe judge timeout: {judge_timeout_s}s")
    print(f"Production answer timeout: {answer_timeout_s:g}s")
    print(f"Repeats per model: {repeats}")
    print(f"Elapsed time: {_format_duration(total_elapsed_s)}")
    print("Timing model: repeat 1 is load+answer; later repeats estimate steady answer time.")
    print("Models exceeding --timeout-s on steady answer time are excluded from passing results.")
    print(f"Expected issue classes: {', '.join(EXPECTED_ISSUE_CLASSES)}")
    print("")

    if not passing:
        print("No models passed every repeat of the fixture-backed audit probe.", flush=True)
        if not args.show_all:
            print("Tip: re-run with --show-all to see per-model failure reasons.", flush=True)
            return 1
        print("")

    if passing:
        print(f"Fastest passing models by steady answer time (top {args.top_n}):")
        for index, summary in enumerate(passing[: max(1, args.top_n)], start=1):
            load_est = (
                "n/a"
                if summary.estimated_load_overhead_s is None
                else f"{summary.estimated_load_overhead_s:.2f}s"
            )
            print(
                f"{index:>2}. {summary.model_id} | size={_format_size(summary.size_hint_b)} "
                f"| first_load+answer={summary.first_latency_s:.2f}s "
                f"| answer_mean={summary.mean_answer_latency_s:.2f}s "
                f"| answer_max={summary.max_answer_latency_s:.2f}s "
                f"| load_est={load_est} "
                f"| all_mean={summary.mean_latency_s:.2f}s "
                f"| pass={summary.pass_count}/{summary.attempts} "
                f"| mean_tokens={summary.mean_tokens_used:.0f} "
                f"| max_violations={summary.max_violations_count}"
            )

    if args.show_all:
        print("")
        print("All results (size-sorted model summaries):")
        for summary in summaries:
            status = "PASS" if summary.passed else "FAIL"
            display_status = _color_status(status, enabled=color_enabled)
            unique_reasons = tuple(dict.fromkeys(summary.reasons))
            load_est = (
                "n/a"
                if summary.estimated_load_overhead_s is None
                else f"{summary.estimated_load_overhead_s:.2f}s"
            )
            reason = ""
            if not summary.passed:
                reasons = [item for item in unique_reasons if item != "ok"]
                if summary.answer_timeout_exceeded:
                    reasons.append(
                        f"answer time exceeded --timeout-s {summary.answer_timeout_s:g}s"
                    )
                reason = " | " + " ; ".join(reasons)
            print(
                f"{display_status} {summary.model_id} | size={_format_size(summary.size_hint_b)} "
                f"| first_load+answer={summary.first_latency_s:.2f}s "
                f"| answer_mean={summary.mean_answer_latency_s:.2f}s "
                f"| answer_max={summary.max_answer_latency_s:.2f}s "
                f"| load_est={load_est} "
                f"| all_mean={summary.mean_latency_s:.2f}s "
                f"| pass={summary.pass_count}/{summary.attempts} "
                f"| mean_tokens={summary.mean_tokens_used:.0f} "
                f"| confidences={','.join(summary.confidences)}"
                f"{reason}"
            )

    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())
