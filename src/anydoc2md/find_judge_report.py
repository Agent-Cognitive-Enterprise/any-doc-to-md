"""Output formatting and summary math for the find_judge CLI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from anydoc2md.judge_probe_models import ModelInfo
from anydoc2md.judge_probe_runner import ProbeResult

_ANSI_GREEN = "\033[32m"
_ANSI_RED = "\033[31m"
_ANSI_RESET = "\033[0m"


@dataclass(frozen=True)
class ModelProbeSummary:
    model_id: str
    size_hint_b: float | None
    attempts: int
    pass_count: int
    first_latency_s: float
    mean_answer_latency_s: float
    max_answer_latency_s: float
    estimated_load_overhead_s: float | None
    answer_timeout_s: float | None
    answer_timeout_exceeded: bool
    mean_latency_s: float
    mean_tokens_used: float
    max_violations_count: int
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.pass_count == self.attempts and not self.answer_timeout_exceeded


@dataclass(frozen=True)
class FindJudgeFinalReport:
    judge_provider: str
    judge_url: str
    models_discovered: int
    models_selected: int
    phase1_summaries: Sequence[ModelProbeSummary]
    phase1_passing: Sequence[ModelProbeSummary]
    phase2_summaries: Sequence[ModelProbeSummary]
    phase2_passing: Sequence[ModelProbeSummary]
    judge_timeout_s: int
    answer_timeout_s: float
    repeats: int
    pass_threshold: float
    stop_on_fail: bool
    show_errors: bool
    show_all: bool
    color_enabled: bool
    phase2_only: bool
    top_n: int
    required_issue_count: int
    expected_issue_ids: Sequence[str]
    phase2_gate_lines: Sequence[str]
    timing_split_available: bool
    total_elapsed_s: float


def _render_progress(current: int, total: int, *, width: int = 24) -> str:
    if total <= 0:
        return "[?] 0/0"
    bounded_width = max(10, min(60, width))
    ratio = min(1.0, max(0.0, current / total))
    filled = int(round(bounded_width * ratio))
    bar = "#" * filled + "-" * (bounded_width - filled)
    return f"[{bar}] {current}/{total}"


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _color_status(status: str, *, enabled: bool) -> str:
    if not enabled:
        return status
    if status == "PASS":
        return f"{_ANSI_GREEN}{status}{_ANSI_RESET}"
    if status == "FAIL":
        return f"{_ANSI_RED}{status}{_ANSI_RESET}"
    return status


def _color_conclusion_line(line: str, *, passed: bool, enabled: bool) -> str:
    if not enabled:
        return line
    color = _ANSI_GREEN if passed else _ANSI_RED
    return f"{color}{line}{_ANSI_RESET}"


def _render_attempt_status(
    current: int,
    total: int,
    *,
    elapsed_s: float,
    eta_s: float,
    status: str,
    color_enabled: bool,
) -> str:
    return (
        f"{_render_progress(current, total)} "
        f"{_format_duration(elapsed_s)}/{_format_duration(eta_s)} "
        f"{_color_status(status, enabled=color_enabled)}"
    )


def _format_load_est(summary: ModelProbeSummary) -> str:
    if summary.estimated_load_overhead_s is None:
        return "n/a"
    return f"{summary.estimated_load_overhead_s:.2f}s"


def _render_model_conclusion(
    summary: ModelProbeSummary,
    *,
    show_errors: bool = False,
) -> str:
    status = "PASS" if summary.passed else "FAIL"
    reasons = [reason for reason in tuple(dict.fromkeys(summary.reasons)) if reason != "ok"]
    if summary.answer_timeout_exceeded:
        reasons.append(f"answer time exceeded --timeout-s {summary.answer_timeout_s:g}s")
    reason = "" if summary.passed or not show_errors else " | " + " ; ".join(reasons)
    return (
        f"MODEL {status} {summary.model_id} | pass={summary.pass_count}/{summary.attempts} "
        f"| first_load+answer={summary.first_latency_s:.2f}s "
        f"| answer_mean={summary.mean_answer_latency_s:.2f}s "
        f"| answer_max={summary.max_answer_latency_s:.2f}s "
        f"| load_est={_format_load_est(summary)}"
        f"{reason}"
    )


def _format_phase_summary(
    summary: ModelProbeSummary,
    *,
    color_enabled: bool,
    show_errors: bool,
) -> str:
    status = "PASS" if summary.passed else "FAIL"
    display_status = _color_status(status, enabled=color_enabled)
    unique_reasons = tuple(dict.fromkeys(summary.reasons))
    load_est = (
        "n/a"
        if summary.estimated_load_overhead_s is None
        else f"{summary.estimated_load_overhead_s:.2f}s"
    )
    reason = ""
    if not summary.passed and show_errors:
        reasons = [item for item in unique_reasons if item != "ok"]
        if summary.answer_timeout_exceeded:
            reasons.append(f"answer time exceeded --timeout-s {summary.answer_timeout_s:g}s")
        reason = " | " + " ; ".join(reasons)
    return (
        f"{display_status} {summary.model_id} | size={_format_size(summary.size_hint_b)} "
        f"| first_load+answer={summary.first_latency_s:.2f}s "
        f"| answer_mean={summary.mean_answer_latency_s:.2f}s "
        f"| answer_max={summary.max_answer_latency_s:.2f}s "
        f"| load_est={load_est} "
        f"| all_mean={summary.mean_latency_s:.2f}s "
        f"| pass={summary.pass_count}/{summary.attempts} "
        f"| mean_tokens={summary.mean_tokens_used:.0f}"
        f"{reason}"
    )


def _format_size(size_hint_b: float | None) -> str:
    if size_hint_b is None:
        return "?"
    if size_hint_b.is_integer():
        return f"{int(size_hint_b)}B"
    return f"{size_hint_b:g}B"


def _summarize_model(
    model: ModelInfo,
    attempt_results: list[ProbeResult],
    *,
    answer_timeout_s: float | None = None,
) -> ModelProbeSummary:
    attempts = len(attempt_results)
    pass_count = sum(1 for result in attempt_results if result.passed)
    first_latency_s = attempt_results[0].latency_s if attempt_results else 0.0
    answer_results = attempt_results[1:] if len(attempt_results) > 1 else attempt_results
    mean_answer_latency_s = (
        sum(result.latency_s for result in answer_results) / max(1, len(answer_results))
    )
    max_answer_latency_s = max((result.latency_s for result in answer_results), default=0.0)
    estimated_load_overhead_s = None
    if len(attempt_results) > 1:
        estimated_load_overhead_s = max(0.0, first_latency_s - mean_answer_latency_s)
    answer_timeout_exceeded = (
        answer_timeout_s is not None and max_answer_latency_s > answer_timeout_s
    )
    mean_latency_s = sum(result.latency_s for result in attempt_results) / max(1, attempts)
    mean_tokens_used = sum(result.tokens_used for result in attempt_results) / max(1, attempts)
    max_violations_count = max((result.violations_count for result in attempt_results), default=0)
    reasons = tuple(result.reason for result in attempt_results)
    return ModelProbeSummary(
        model_id=model.model_id,
        size_hint_b=model.size_hint_b,
        attempts=attempts,
        pass_count=pass_count,
        first_latency_s=first_latency_s,
        mean_answer_latency_s=mean_answer_latency_s,
        max_answer_latency_s=max_answer_latency_s,
        estimated_load_overhead_s=estimated_load_overhead_s,
        answer_timeout_s=answer_timeout_s,
        answer_timeout_exceeded=answer_timeout_exceeded,
        mean_latency_s=mean_latency_s,
        mean_tokens_used=mean_tokens_used,
        max_violations_count=max_violations_count,
        reasons=reasons,
    )


def print_final_report(report: FindJudgeFinalReport) -> bool:
    passing = report.phase2_passing

    print(f"Judge provider: {report.judge_provider}")
    print(f"Judge URL: {report.judge_url}")
    print(f"Models discovered: {report.models_discovered}")
    print(f"Models selected: {report.models_selected}")
    if report.phase2_only:
        print("Models passing phase 1 checklist: skipped (--phase2-only)")
    else:
        print(f"Models passing phase 1 checklist: {len(report.phase1_passing)}")
    print(f"Models passing phase 2 freeform: {len(report.phase2_passing)}")
    print(f"Probe judge timeout: {report.judge_timeout_s}s")
    print(f"Production answer timeout: {report.answer_timeout_s:g}s")
    print(f"Repeats per model: {report.repeats}")
    print(f"Pass threshold: {report.pass_threshold:.2f}")
    print(f"Stop on first fail: {'yes' if report.stop_on_fail else 'no'}")
    print(f"Show diagnostic errors: {'yes' if report.show_errors else 'no'}")
    print(f"Phase 2 only: {'yes' if report.phase2_only else 'no'}")
    if not report.phase2_only:
        print(
            f"Phase 1 checklist gate: find at least {report.required_issue_count}/"
            f"{len(report.expected_issue_ids)} expected checklist issues."
        )
    print(
        f"Repeat criteria: {report.repeats}/{report.repeats} repeats pass with no steady "
        f"answer above {report.answer_timeout_s:g}s."
    )
    print("Phase 2 freeform gate:")
    for line in report.phase2_gate_lines:
        print(f"  {line}")
    print(
        "Timing split: "
        + (
            "repeat 1 measures load+answer; later repeats estimate steady answer and load_est."
            if report.timing_split_available
            else "with repeats=1 only load+answer is measured; load and answer cannot be separated."
        )
    )
    print(f"Elapsed time: {_format_duration(report.total_elapsed_s)}")
    print("Models exceeding --timeout-s on steady answer time are excluded from passing results.")
    print(f"Expected checklist issue IDs: {', '.join(report.expected_issue_ids)}")
    print("")

    if not passing:
        if not report.phase2_only and not report.phase1_passing:
            print("No models passed the phase-1 checklist shortlist.", flush=True)
        else:
            print("No shortlisted models passed the phase-2 freeform probe.", flush=True)
        if not report.show_errors:
            print(
                "Tip: re-run with --show-all --show-errors to see per-model failure reasons.",
                flush=True,
            )
        if not report.show_all:
            return False
        print("")

    if passing:
        print(f"Fastest models passing both phases by steady answer time (top {report.top_n}):")
        for index, summary in enumerate(passing[: max(1, report.top_n)], start=1):
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
                f"| max_issues={summary.max_violations_count}"
            )

    if report.show_all:
        print("")
        if report.phase1_summaries:
            print("Phase 1 results (size-sorted model summaries):")
            for summary in report.phase1_summaries:
                print(
                    _format_phase_summary(
                        summary,
                        color_enabled=report.color_enabled,
                        show_errors=report.show_errors,
                    )
                )
        if report.phase2_summaries:
            if report.phase1_summaries:
                print("")
            print("Phase 2 results (shortlisted models):")
            for summary in report.phase2_summaries:
                print(
                    _format_phase_summary(
                        summary,
                        color_enabled=report.color_enabled,
                        show_errors=report.show_errors,
                    )
                )

    return bool(passing)
