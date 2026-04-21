"""Stage runner for the find_judge CLI."""

from __future__ import annotations

import time
from collections.abc import Callable

from anydoc2md.find_judge_report import (
    _color_conclusion_line,
    _format_size,
    _render_attempt_status,
    _render_model_conclusion,
    _render_progress,
    _summarize_model,
    ModelProbeSummary,
)
from anydoc2md.judge_probe_models import ModelInfo
from anydoc2md.judge_probe_runner import ProbeResult

AttemptRunner = Callable[[ModelInfo], ProbeResult]


def run_probe_stage(
    *,
    models: list[ModelInfo],
    repeats: int,
    answer_timeout_s: float,
    stop_on_fail: bool,
    color_enabled: bool,
    show_errors: bool,
    attempt_runner: AttemptRunner,
) -> tuple[list[ModelProbeSummary], list[ModelProbeSummary]]:
    total_attempts = len(models) * repeats
    stage_started_at = time.monotonic()
    results: list[ProbeResult] = []
    completed_attempts = 0

    for model_index, model in enumerate(models, start=1):
        model_attempt_results: list[ProbeResult] = []
        for repeat_index in range(1, repeats + 1):
            timing_label = "load+answer" if repeat_index == 1 else "answer"
            prefix = (
                f"{_render_progress(completed_attempts, total_attempts)} "
                f"model {model_index}/{len(models)} repeat={repeat_index}/{repeats} "
                f"{model.model_id} (size={_format_size(model.size_hint_b)})..."
            )
            print(prefix, end="", flush=True)
            result = attempt_runner(model)
            completed_attempts += 1
            elapsed_s = time.monotonic() - stage_started_at
            mean_attempt_s = elapsed_s / max(1, completed_attempts)
            remaining_attempts = total_attempts - completed_attempts
            eta_s = mean_attempt_s * remaining_attempts
            answer_timed_out = (
                result.latency_s > answer_timeout_s
                and (repeat_index > 1 or repeats == 1)
            )
            attempt_failed = (not result.passed) or answer_timed_out
            status = "FAIL" if attempt_failed else "PASS"
            speed_note = f" | answer>{answer_timeout_s:g}s" if answer_timed_out else ""
            reason = "" if result.passed or not show_errors else f" | {result.reason}"
            print(
                f"\r{_render_attempt_status(completed_attempts, total_attempts, elapsed_s=elapsed_s, eta_s=eta_s, status=status, color_enabled=color_enabled)} "
                f"{model.model_id} | repeat={repeat_index}/{repeats} "
                f"| {timing_label}={result.latency_s:.2f}s | tokens={result.tokens_used} "
                f"| issues={result.violations_count}{speed_note}{reason}",
                flush=True,
            )
            results.append(result)
            model_attempt_results.append(result)
            if stop_on_fail and attempt_failed:
                completed_attempts += repeats - repeat_index
                break
        summary = _summarize_model(
            model,
            model_attempt_results,
            answer_timeout_s=answer_timeout_s,
        )
        if summary.passed:
            print(
                _color_conclusion_line(
                    _render_model_conclusion(summary, show_errors=show_errors),
                    passed=True,
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
    return summaries, passing
