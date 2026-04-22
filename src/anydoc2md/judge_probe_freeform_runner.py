"""Phase-2 freeform judge runner."""

from __future__ import annotations

import time

from anydoc2md.judge_probe_freeform import run_freeform_probe
from anydoc2md.judge_probe_freeform_case import FreeformProbeSuite
from anydoc2md.judge_probe_models import ModelInfo
from anydoc2md.judge_probe_runner import ProbeResult
from anydoc2md.settings import (
    DEFAULT_CLAUDE_ANTHROPIC_VERSION,
    JUDGE_PROVIDER_LM_STUDIO,
    JudgeSettings,
)


def probe_freeform_model(
    *,
    model: ModelInfo,
    judge_url: str,
    judge_timeout_s: int,
    suite: FreeformProbeSuite,
    judge_provider: str = JUDGE_PROVIDER_LM_STUDIO,
    judge_api_key: str = "",
    anthropic_version: str = DEFAULT_CLAUDE_ANTHROPIC_VERSION,
) -> ProbeResult:
    settings = JudgeSettings(
        url=judge_url,
        model=model.model_id,
        provider=judge_provider,
        api_key=judge_api_key,
        timeout_s=judge_timeout_s,
        anthropic_version=anthropic_version,
    )
    t0 = time.perf_counter()
    verdict = run_freeform_probe(suite=suite, settings=settings)
    latency_s = max(0.0, time.perf_counter() - t0)

    if not verdict.succeeded:
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=verdict.tokens_used,
            violations_count=0,
            passed=False,
            reason=verdict.error or "freeform probe returned error",
        )

    matched_total = sum(score.matched_count for score in verdict.case_scores)
    failing_scores = [score for score in verdict.case_scores if not score.passed]
    if failing_scores:
        reason = " ; ".join(
            (
                f"{score.case_id} matched {score.matched_count}/{score.total_gold_issues} "
                f"gold issues with {score.false_positive_count} false positive(s); "
                f"need at least {score.min_expected_findings} and at most "
                f"{score.max_false_positives}"
            )
            for score in failing_scores
        )
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=latency_s,
            tokens_used=verdict.tokens_used,
            violations_count=matched_total,
            passed=False,
            reason=reason,
        )

    return ProbeResult(
        model_id=model.model_id,
        size_hint_b=model.size_hint_b,
        latency_s=latency_s,
        tokens_used=verdict.tokens_used,
        violations_count=matched_total,
        passed=True,
        reason="ok",
    )
