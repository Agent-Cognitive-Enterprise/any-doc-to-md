"""Judge model probing runner: call the LLM judge and evaluate pass/fail."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from anydoc2md.judge_probe_case import (
    CONTROL_ISSUE_IDS,
    DEFAULT_PASS_THRESHOLD,
    EXPECTED_ISSUE_IDS,
    ProbeCase,
)
from anydoc2md.judge_probe_checklist import run_checklist_probe
from anydoc2md.judge_probe_models import ModelInfo
from anydoc2md.settings import (
    DEFAULT_CLAUDE_ANTHROPIC_VERSION,
    JUDGE_PROVIDER_LM_STUDIO,
    JudgeSettings,
)


@dataclass(frozen=True)
class ProbeResult:
    model_id: str
    size_hint_b: float | None
    latency_s: float
    tokens_used: int
    violations_count: int
    passed: bool
    reason: str


def probe_one_model(
    *,
    model: ModelInfo,
    judge_url: str,
    judge_timeout_s: int,
    probe_case: ProbeCase,
    min_expected_issues: int | None = None,
    judge_provider: str = JUDGE_PROVIDER_LM_STUDIO,
    judge_api_key: str = "",
    anthropic_version: str = DEFAULT_CLAUDE_ANTHROPIC_VERSION,
) -> ProbeResult:
    required_issues = min_expected_issues or max(
        1,
        math.floor(len(EXPECTED_ISSUE_IDS) * DEFAULT_PASS_THRESHOLD),
    )
    settings = JudgeSettings(
        url=judge_url,
        model=model.model_id,
        provider=judge_provider,
        api_key=judge_api_key,
        timeout_s=judge_timeout_s,
        anthropic_version=anthropic_version,
    )
    t0 = time.perf_counter()
    verdict = run_checklist_probe(probe_case=probe_case, settings=settings)
    latency_s = max(0.0, time.perf_counter() - t0)

    tokens_used = verdict.tokens_used
    expected_found = [issue_id for issue_id in EXPECTED_ISSUE_IDS if verdict.issues.get(issue_id)]
    false_controls = [issue_id for issue_id in CONTROL_ISSUE_IDS if verdict.issues.get(issue_id)]
    violations_count = len(expected_found)

    if not verdict.succeeded:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            violations_count=violations_count,
            passed=False,
            reason=verdict.error or "checklist probe returned error",
        )

    if false_controls:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            violations_count=violations_count,
            passed=False,
            reason="false positives on control issues: " + ", ".join(false_controls),
        )

    if violations_count < required_issues:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=tokens_used,
            violations_count=violations_count,
            passed=False,
            reason=(
                f"checklist detected {violations_count}/{len(EXPECTED_ISSUE_IDS)} "
                f"expected issues; need at least {required_issues}: "
                + ", ".join(expected_found or ["none"])
            ),
        )

    return ProbeResult(
        model_id=model.model_id,
        size_hint_b=model.size_hint_b,
        latency_s=latency_s,
        tokens_used=tokens_used,
        violations_count=violations_count,
        passed=True,
        reason="ok",
    )
