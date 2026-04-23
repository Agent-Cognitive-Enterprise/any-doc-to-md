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
from typing import Any

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
from anydoc2md._llm_judge_types import JudgeCallResult, JudgeVerdict, JudgeViolation
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    DEFAULT_JUDGE_TEMPERATURE,
    JUDGE_PROVIDER_CLAUDE,
    JUDGE_PROVIDER_LM_STUDIO,
    JUDGE_PROVIDER_OPENAI,
    JudgeSettings,
    load_judge_settings_from_env,
)


def _call_lm_studio(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    """
    Send a judge request to the configured provider endpoint.

    Returns a JudgeCallResult. The result still supports legacy tuple-unpacking
    as (response_text, tokens_used).
    Raises on network failure.
    """
    if settings.provider == JUDGE_PROVIDER_CLAUDE:
        return _call_claude_messages(system, user, settings)
    return _call_openai_compatible(system, user, settings)


def _call_openai_compatible(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    """Send a chat completion request to an OpenAI-compatible endpoint."""
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
    }
    if settings.provider == JUDGE_PROVIDER_LM_STUDIO and settings.disable_thinking:
        # LM Studio exposes this Qwen3 knob; public provider APIs may reject it.
        payload["chat_template_kwargs"] = {"thinking": False}

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    resp = _post_openai_chat_completions(
        payload=payload,
        headers=headers,
        settings=settings,
    )
    if _should_retry_chat_completions_with_max_completion_tokens(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload["max_completion_tokens"] = retry_payload.pop("max_tokens")
        resp = _post_openai_chat_completions(
            payload=retry_payload,
            headers=headers,
            settings=settings,
        )
        payload = retry_payload
    if _should_retry_chat_completions_without_temperature(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload.pop("temperature", None)
        resp = _post_openai_chat_completions(
            payload=retry_payload,
            headers=headers,
            settings=settings,
        )
    if _should_use_openai_responses_api(resp=resp, settings=settings):
        return _call_openai_responses(system, user, settings)
    resp.raise_for_status()
    data = resp.json()

    text = _message_content_text(data["choices"][0]["message"]["content"])
    usage = data.get("usage", {})
    input_tokens = _int_usage_value(usage.get("prompt_tokens", usage.get("input_tokens", 0)))
    output_tokens = _int_usage_value(
        usage.get("completion_tokens", usage.get("output_tokens", 0))
    )
    tokens = _int_usage_value(usage.get("total_tokens", input_tokens + output_tokens))
    if tokens == 0:
        tokens = input_tokens + output_tokens
    return JudgeCallResult(
        text=text,
        tokens_used=tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _post_openai_chat_completions(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    settings: JudgeSettings,
) -> requests.Response:
    return requests.post(
        f"{settings.url.rstrip('/')}/chat/completions",
        json=payload,
        headers=headers,
        timeout=settings.timeout_s,
    )


def _call_openai_responses(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    """Send a request to the OpenAI Responses API."""
    payload = {
        "model": settings.model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user}],
            },
        ],
        "max_output_tokens": settings.max_tokens,
    }
    if settings.temperature != DEFAULT_JUDGE_TEMPERATURE:
        payload["temperature"] = settings.temperature
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    resp = _post_openai_responses(payload=payload, headers=headers, settings=settings)
    if _should_retry_openai_responses_without_temperature(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload.pop("temperature", None)
        resp = _post_openai_responses(payload=retry_payload, headers=headers, settings=settings)
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    input_tokens = _int_usage_value(usage.get("input_tokens", 0))
    output_tokens = _int_usage_value(usage.get("output_tokens", 0))
    total_tokens = _int_usage_value(usage.get("total_tokens", input_tokens + output_tokens))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return JudgeCallResult(
        text=_responses_output_text(data),
        tokens_used=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _post_openai_responses(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    settings: JudgeSettings,
) -> requests.Response:
    return requests.post(
        f"{settings.url.rstrip('/')}/responses",
        json=payload,
        headers=headers,
        timeout=settings.timeout_s,
    )


def _call_claude_messages(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> JudgeCallResult:
    """Send a request to Anthropic's Messages API."""
    payload = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.api_key,
        "anthropic-version": settings.anthropic_version,
    }
    resp = requests.post(
        _claude_messages_url(settings.url),
        json=payload,
        headers=headers,
        timeout=settings.timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()

    text = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )
    usage = data.get("usage", {})
    input_tokens = (
        _int_usage_value(usage.get("input_tokens", 0))
        + _int_usage_value(usage.get("cache_creation_input_tokens", 0))
        + _int_usage_value(usage.get("cache_read_input_tokens", 0))
    )
    output_tokens = _int_usage_value(usage.get("output_tokens", 0))
    return JudgeCallResult(
        text=text,
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _claude_messages_url(url: str) -> str:
    stripped = url.rstrip("/")
    if stripped.endswith("/v1"):
        return f"{stripped}/messages"
    return stripped


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )
    return "" if content is None else str(content)


def _responses_output_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for output_item in data.get("output", []):
        if not isinstance(output_item, dict) or output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") == "output_text":
                parts.append(str(content_item.get("text", "")))
    return "".join(parts)


def _should_use_openai_responses_api(
    *,
    resp: requests.Response,
    settings: JudgeSettings,
) -> bool:
    if settings.provider != JUDGE_PROVIDER_OPENAI or resp.status_code != 404:
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    error = data.get("error", {})
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", "")).lower()
    if "only supported in v1/responses" in message and "v1/chat/completions" in message:
        return True
    return "not a chat model" in message and "v1/chat/completions" in message


def _should_retry_openai_responses_without_temperature(
    *,
    resp: requests.Response,
    payload: dict[str, Any],
) -> bool:
    if resp.status_code != 400 or "temperature" not in payload:
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    error = data.get("error", {})
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", "")).lower()
    return "unsupported parameter" in message and "temperature" in message


def _should_retry_chat_completions_with_max_completion_tokens(
    *,
    resp: requests.Response,
    payload: dict[str, Any],
) -> bool:
    if resp.status_code != 400 or "max_tokens" not in payload:
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    error = data.get("error", {})
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", "")).lower()
    return (
        "unsupported parameter" in message
        and "max_tokens" in message
        and "max_completion_tokens" in message
    )


def _should_retry_chat_completions_without_temperature(
    *,
    resp: requests.Response,
    payload: dict[str, Any],
) -> bool:
    if resp.status_code != 400 or "temperature" not in payload:
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    error = data.get("error", {})
    if not isinstance(error, dict):
        return False
    message = str(error.get("message", "")).lower()
    if "temperature" not in message:
        return False
    return (
        "unsupported parameter" in message
        or "unsupported value" in message
        or "only the default (1) value is supported" in message
    )


def _int_usage_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
