"""
CLI helper: find a local model that can do ADTM judge work (audit prompt).

This probes a configured judge provider by:
1) Fetching model ids from the provider's /models endpoint
2) Sorting by a best-effort size hint parsed from the model id string
3) Running a fixed checklist probe to shortlist reliable models
4) Running a freeform issue-discovery probe on the shortlist
5) Reporting the fastest models that pass both phases (top 10 by default)
"""
from __future__ import annotations

import math
import sys
import time

from anydoc2md.find_judge_args import (
    DEFAULT_PROBE_JUDGE_TIMEOUT_S,
    build_argument_parser,
)
from anydoc2md.judge_probe_case import EXPECTED_ISSUE_IDS
from anydoc2md.find_judge_provider import (
    fetch_judge_model_ids,
    judge_model_listing_url,
    resolve_judge_provider_config,
)
from anydoc2md.find_judge_stage import run_probe_stage
from anydoc2md.find_judge_report import (
    _color_status,
    _format_duration,
    _render_attempt_status,
    _render_progress,
    _summarize_model,
    FindJudgeFinalReport,
    print_final_report,
)
from anydoc2md.find_judge_support import (
    _env_int,
    _print_artifact_paths,
    _probe_case_context,
    _select_models,
)
from anydoc2md.judge_probe_freeform_case import freeform_gate_lines
from anydoc2md.judge_probe_freeform_runner import probe_freeform_model
from anydoc2md.judge_probe_models import ModelInfo, parse_size_hint_billions
from anydoc2md.judge_probe_runner import probe_one_model
from anydoc2md.settings import ENV_JUDGE_TIMEOUT_S


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        provider_config = resolve_judge_provider_config(
            provider_arg=args.judge_provider,
            url_arg=args.judge_url,
        )
    except Exception as exc:
        print(f"Error: {exc}", flush=True)
        return 2
    judge_provider = provider_config.provider
    judge_url = provider_config.url
    judge_api_key = provider_config.api_key
    anthropic_version = provider_config.anthropic_version

    env_timeout = _env_int(ENV_JUDGE_TIMEOUT_S)
    judge_timeout_s = (
        args.judge_timeout_s
        if args.judge_timeout_s is not None
        else (env_timeout if env_timeout is not None else DEFAULT_PROBE_JUDGE_TIMEOUT_S)
    )
    repeats = args.repeats
    pass_threshold = args.pass_threshold
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
    if pass_threshold <= 0 or pass_threshold > 1:
        print("Error: pass-threshold must be > 0 and <= 1.", flush=True)
        return 2
    required_issue_count = max(1, math.floor(len(EXPECTED_ISSUE_IDS) * pass_threshold))
    timing_split_available = repeats > 1

    print(f"Judge provider: {judge_provider}", flush=True)
    print(f"Fetching models from: {judge_model_listing_url(provider_config)}", flush=True)
    try:
        model_ids = fetch_judge_model_ids(provider_config)
    except Exception as exc:
        print(f"Error: unable to fetch models from {judge_url!r}: {exc}", flush=True)
        return 2

    if not model_ids:
        print(
            f"Error: no models returned by {judge_model_listing_url(provider_config)}",
            flush=True,
        )
        return 2

    if args.list_models_only:
        print(f"Models discovered: {len(model_ids)}", flush=True)
        for model_id in model_ids:
            print(model_id, flush=True)
        return 0

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
    print(f"Pass threshold: {pass_threshold:.2f}", flush=True)
    print(f"Stop on first fail: {'yes' if args.stop_on_fail else 'no'}", flush=True)
    print(f"Show diagnostic errors: {'yes' if args.show_errors else 'no'}", flush=True)
    print(f"Phase 2 only: {'yes' if args.phase2_only else 'no'}", flush=True)
    if not args.phase2_only:
        print(
            f"Phase 1 checklist gate: find at least {required_issue_count}/"
            f"{len(EXPECTED_ISSUE_IDS)} expected checklist issues.",
            flush=True,
        )
    print(
        f"Repeat criteria: {repeats}/{repeats} repeats pass with no steady answer "
        f"above {answer_timeout_s:g}s.",
        flush=True,
    )
    print(
        "Timing split: "
        + (
            "repeat 1 measures load+answer; later repeats estimate steady answer and load_est."
            if timing_split_available
            else "with repeats=1 only load+answer is measured; load and answer cannot be separated."
        ),
        flush=True,
    )

    keep_artifacts = bool(args.keep_artifacts or args.artifacts_dir)
    run_started_at = time.monotonic()

    with _probe_case_context(
        keep_artifacts=keep_artifacts,
        artifacts_dir=args.artifacts_dir,
    ) as (probe_case, freeform_suite, probe_case_dir):
        _print_artifact_paths(probe_case, freeform_suite, probe_case_dir)

        if args.phase2_only:
            phase1_summaries = []
            phase1_passing = []
            phase2_models = models
            print("Phase 2/2: Freeform issue discovery", flush=True)
            print("Phase 1 skipped: using selected models as the phase-2 shortlist.", flush=True)
        else:
            print("Phase 1/2: Checklist shortlist", flush=True)
            phase1_summaries, phase1_passing = run_probe_stage(
                models=models,
                repeats=repeats,
                answer_timeout_s=answer_timeout_s,
                stop_on_fail=args.stop_on_fail,
                color_enabled=color_enabled,
                show_errors=args.show_errors,
                attempt_runner=lambda model: probe_one_model(
                    model=model,
                    judge_url=judge_url,
                    judge_timeout_s=judge_timeout_s,
                    probe_case=probe_case,
                    min_expected_issues=required_issue_count,
                    judge_provider=judge_provider,
                    judge_api_key=judge_api_key,
                    anthropic_version=anthropic_version,
                ),
            )
            phase2_models = [
                model
                for model in models
                if any(summary.model_id == model.model_id for summary in phase1_passing)
            ]
            if phase2_models:
                print("", flush=True)
                print(
                    f"Phase 1 shortlist complete: {len(phase1_passing)} model(s) passed.",
                    flush=True,
                )
                print("Phase 2/2: Freeform issue discovery", flush=True)

        if phase2_models:
            print("Phase 2 gate:", flush=True)
            for line in freeform_gate_lines(freeform_suite):
                print(f"  {line}", flush=True)
            print(
                "Phase 2 prompt audits one candidate at a time; no checklist is exposed.",
                flush=True,
            )
            phase2_summaries, phase2_passing = run_probe_stage(
                models=phase2_models,
                repeats=repeats,
                answer_timeout_s=answer_timeout_s,
                stop_on_fail=args.stop_on_fail,
                color_enabled=color_enabled,
                show_errors=args.show_errors,
                attempt_runner=lambda model: probe_freeform_model(
                    model=model,
                    judge_url=judge_url,
                    judge_timeout_s=judge_timeout_s,
                    suite=freeform_suite,
                    judge_provider=judge_provider,
                    judge_api_key=judge_api_key,
                    anthropic_version=anthropic_version,
                ),
            )
        else:
            phase2_summaries = []
            phase2_passing = []

    total_elapsed_s = time.monotonic() - run_started_at
    report = FindJudgeFinalReport(
        judge_provider=judge_provider,
        judge_url=judge_url,
        models_discovered=len(model_ids),
        models_selected=len(models),
        phase1_summaries=phase1_summaries,
        phase1_passing=phase1_passing,
        phase2_summaries=phase2_summaries,
        phase2_passing=phase2_passing,
        judge_timeout_s=judge_timeout_s,
        answer_timeout_s=answer_timeout_s,
        repeats=repeats,
        pass_threshold=pass_threshold,
        stop_on_fail=args.stop_on_fail,
        show_errors=args.show_errors,
        show_all=args.show_all,
        color_enabled=color_enabled,
        phase2_only=args.phase2_only,
        top_n=args.top_n,
        required_issue_count=required_issue_count,
        expected_issue_ids=EXPECTED_ISSUE_IDS,
        phase2_gate_lines=tuple(freeform_gate_lines(freeform_suite)),
        timing_split_available=timing_split_available,
        total_elapsed_s=total_elapsed_s,
    )
    return 0 if print_final_report(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
