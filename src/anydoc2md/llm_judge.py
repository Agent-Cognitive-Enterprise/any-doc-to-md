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

from anydoc2md._llm_judge_client import (
    call_claude_messages as _client_call_claude_messages,
    call_judge_provider as _client_call_judge_provider,
    call_openai_compatible as _client_call_openai_compatible,
    call_openai_responses as _client_call_openai_responses,
    claude_messages_url as _client_claude_messages_url,
)
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
from anydoc2md._llm_judge_types import JudgeCallResult, JudgeVerdict, JudgeViolation
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
) -> JudgeCallResult:
    return _client_call_judge_provider(system, user, settings, requests_module=requests)


def _call_openai_compatible(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    return _client_call_openai_compatible(system, user, settings, requests_module=requests)


def _call_openai_responses(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    return _client_call_openai_responses(system, user, settings, requests_module=requests)


def _call_claude_messages(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    return _client_call_claude_messages(system, user, settings, requests_module=requests)


def _claude_messages_url(url: str) -> str:
    return _client_claude_messages_url(url)


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
        call_result = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"Judge call failed: {exc}",
        )

    return _parse_verdict(
        call_result.text,
        candidates,
        judge_settings.model,
        call_result.tokens_used,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
    )


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
        call_result = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used=judge_settings.model,
            tokens_used=0,
            error=f"Judge call failed: {exc}",
        )
    return _parse_verdict(
        call_result.text,
        [candidate],
        judge_settings.model,
        call_result.tokens_used,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
    )
