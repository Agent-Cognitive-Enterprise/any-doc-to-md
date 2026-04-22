"""
LLM judge — audit candidate outputs and break ties when needed.

This module supports two related tasks:
- auditing a selected candidate against source context
- breaking ties between multiple near-tied candidates

Fallback behavior: when the LLM call fails (network, timeout, bad JSON), the
returned verdict has confidence="error" and an error message. Callers should
fall back to score-based selection.

Usage:
    from anydoc2md.llm_judge import judge_candidate_against_source
    from anydoc2md.settings import JudgeSettings

    settings = JudgeSettings(
        url="http://127.0.0.1:1234/v1",
        model="qwen/qwen3.6-35b-a3b",
    )

    verdict = judge_candidate_against_source(
        candidate,
        source_path,
        traits,
        audit_pdf_path=candidate.staging_dir / "audit_candidate.pdf",
        settings=settings,
    )
"""

from __future__ import annotations

from pathlib import Path

import requests

from anydoc2md._llm_judge_parsing import _parse_verdict, _parse_violations
from anydoc2md._llm_judge_pdf_issue_localizer import (
    detect_pdf_suspected_issues,
)
from anydoc2md._llm_judge_pdf_issue_reviewer import (
    judge_candidate_against_source_issues,
)
from anydoc2md._llm_judge_prompting import (
    EXCERPT_CHARS_PER_ADAPTER,
    _evidence_block,
    _excerpt,
    _traits_summary,
    build_audit_prompt,
    build_prompt,
)
from anydoc2md._llm_judge_types import JudgeVerdict, JudgeViolation
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
)


def _call_lm_studio(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> tuple[str, int]:
    """
    Send a chat completion request to an OpenAI-compatible endpoint.

    Returns (response_text, tokens_used).
    Raises on network failure.
    """
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        # chat_template_kwargs disables thinking mode on Qwen3 models,
        # ensuring the JSON response lands in content (not reasoning_content).
        "chat_template_kwargs": {"thinking": False} if settings.disable_thinking else {},
    }

    resp = requests.post(
        f"{settings.url.rstrip('/')}/chat/completions",
        json=payload,
        timeout=settings.timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


def judge_near_tie(
    candidates: list[AdapterResult],
    source_path: Path,
    traits: DocumentTraits,
    *,
    settings: JudgeSettings | None = None,
) -> JudgeVerdict:
    """
    Ask the LLM judge to select the best conversion among near-tied adapters.

    Returns:
        JudgeVerdict. On network/parse failure, confidence=="error" and
        preferred_adapter=="" — caller should fall back to score-based winner.
    """
    if len(candidates) < 2:
        name = candidates[0].method_name if candidates else ""
        return JudgeVerdict(
            preferred_adapter=name,
            confidence="high",
            reasoning="Only one candidate — no judging needed.",
            notes={},
            model_used="",
            tokens_used=0,
        )

    try:
        judge_settings = settings or load_judge_settings_from_env()
    except AnyDocToMdConfigError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="",
            tokens_used=0,
            error=str(exc),
        )

    system, user = build_prompt(candidates, traits)

    try:
        raw, tokens = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )

    return _parse_verdict(raw, candidates, judge_settings.model, tokens)


def judge_candidate_against_source(
    candidate: AdapterResult,
    source_path: Path,
    traits: DocumentTraits,
    *,
    audit_pdf_path: Path,
    settings: JudgeSettings | None = None,
) -> JudgeVerdict:
    """Audit one selected candidate against source context."""
    try:
        judge_settings = settings or load_judge_settings_from_env()
    except AnyDocToMdConfigError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="",
            tokens_used=0,
            error=str(exc),
        )

    if source_path.suffix.lower() == ".pdf" and audit_pdf_path.suffix.lower() == ".pdf":
        try:
            issues = detect_pdf_suspected_issues(source_path, audit_pdf_path)
        except Exception:
            issues = None
        if issues == []:
            return JudgeVerdict(
                preferred_adapter=candidate.method_name,
                confidence="high",
                reasoning=(
                    "Deterministic source/candidate PDF checks found no suspicious "
                    "windows that required LLM review."
                ),
                notes={candidate.method_name: "No deterministic PDF issues detected."},
                model_used="",
                tokens_used=0,
                violations=[],
                window_verdicts=[],
                overall_confidence=0.95,
                uncertainty_note="PDF audit short-circuited: no deterministic suspect windows.",
                error="",
            )
        if issues:
            return judge_candidate_against_source_issues(
                candidate=candidate,
                traits=traits,
                issues=issues,
                settings=judge_settings,
                call_lm_studio=_call_lm_studio,
            )

    system, user = build_audit_prompt(candidate, source_path, traits, audit_pdf_path)
    try:
        raw, tokens = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )
    return _parse_verdict(raw, [candidate], judge_settings.model, tokens)
