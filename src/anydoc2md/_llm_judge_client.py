"""Provider-specific HTTP client helpers for the LLM judge."""

from __future__ import annotations

from typing import Any

import requests as default_requests

from anydoc2md._llm_judge_types import JudgeCallResult
from anydoc2md.settings import (
    DEFAULT_JUDGE_TEMPERATURE,
    JUDGE_PROVIDER_CLAUDE,
    JUDGE_PROVIDER_LM_STUDIO,
    JUDGE_PROVIDER_OPENAI,
    JudgeSettings,
)


def call_judge_provider(
    system: str,
    user: str,
    settings: JudgeSettings,
    *,
    requests_module: Any = default_requests,
) -> JudgeCallResult:
    """
    Send a judge request to the configured provider endpoint.

    Returns a JudgeCallResult. The result still supports legacy tuple-unpacking
    as (response_text, tokens_used). Raises on network failure.
    """
    if settings.provider == JUDGE_PROVIDER_CLAUDE:
        return call_claude_messages(system, user, settings, requests_module=requests_module)
    return call_openai_compatible(system, user, settings, requests_module=requests_module)


def call_openai_compatible(
    system: str,
    user: str,
    settings: JudgeSettings,
    *,
    requests_module: Any = default_requests,
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
        requests_module=requests_module,
    )
    if _should_retry_chat_completions_with_max_completion_tokens(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload["max_completion_tokens"] = retry_payload.pop("max_tokens")
        resp = _post_openai_chat_completions(
            payload=retry_payload,
            headers=headers,
            settings=settings,
            requests_module=requests_module,
        )
        payload = retry_payload
    if _should_retry_chat_completions_without_temperature(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload.pop("temperature", None)
        resp = _post_openai_chat_completions(
            payload=retry_payload,
            headers=headers,
            settings=settings,
            requests_module=requests_module,
        )
    if _should_use_openai_responses_api(resp=resp, settings=settings):
        return call_openai_responses(system, user, settings, requests_module=requests_module)
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


def call_openai_responses(
    system: str,
    user: str,
    settings: JudgeSettings,
    *,
    requests_module: Any = default_requests,
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

    resp = _post_openai_responses(
        payload=payload,
        headers=headers,
        settings=settings,
        requests_module=requests_module,
    )
    if _should_retry_openai_responses_without_temperature(resp=resp, payload=payload):
        retry_payload = dict(payload)
        retry_payload.pop("temperature", None)
        resp = _post_openai_responses(
            payload=retry_payload,
            headers=headers,
            settings=settings,
            requests_module=requests_module,
        )
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


def call_claude_messages(
    system: str,
    user: str,
    settings: JudgeSettings,
    *,
    requests_module: Any = default_requests,
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
    resp = requests_module.post(
        claude_messages_url(settings.url),
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


def claude_messages_url(url: str) -> str:
    stripped = url.rstrip("/")
    if stripped.endswith("/v1"):
        return f"{stripped}/messages"
    return stripped


def _post_openai_chat_completions(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    settings: JudgeSettings,
    requests_module: Any,
):
    return requests_module.post(
        f"{settings.url.rstrip('/')}/chat/completions",
        json=payload,
        headers=headers,
        timeout=settings.timeout_s,
    )


def _post_openai_responses(
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    settings: JudgeSettings,
    requests_module: Any,
):
    return requests_module.post(
        f"{settings.url.rstrip('/')}/responses",
        json=payload,
        headers=headers,
        timeout=settings.timeout_s,
    )


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
    resp,
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
    resp,
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
    resp,
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
    resp,
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
