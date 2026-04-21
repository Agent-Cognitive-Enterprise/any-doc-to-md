"""Output formatting and summary math for the find_judge CLI."""

from __future__ import annotations

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
    confidences: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.pass_count == self.attempts and not self.answer_timeout_exceeded


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
    confidences = tuple(result.confidence for result in attempt_results)
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
        confidences=confidences,
        reasons=reasons,
    )
