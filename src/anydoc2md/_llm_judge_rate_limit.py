"""Provider-aware retry delay helpers for LLM judge rate limits."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from anydoc2md.settings import (
    JUDGE_PROVIDER_CLAUDE,
    JUDGE_PROVIDER_DEEPSEEK,
    JUDGE_PROVIDER_LM_STUDIO,
    JUDGE_PROVIDER_OPENAI,
    JudgeSettings,
)

HTTP_TOO_MANY_REQUESTS = 429

_RATE_LIMIT_FALLBACK_BASE_S = {
    JUDGE_PROVIDER_CLAUDE: 8.0,
    JUDGE_PROVIDER_OPENAI: 2.0,
    JUDGE_PROVIDER_DEEPSEEK: 2.0,
    JUDGE_PROVIDER_LM_STUDIO: 0.5,
}


def rate_limit_retry_delay_s(
    exc: Exception,
    *,
    attempt: int,
    settings: JudgeSettings,
) -> float:
    """Return provider-aware retry delay for HTTP 429 errors."""
    if _http_status_code(exc) != HTTP_TOO_MANY_REQUESTS:
        return 0.0

    headers = _response_headers(exc)
    retry_after_delay = _retry_after_delay_s(headers.get("retry-after", ""))
    if retry_after_delay is not None:
        return retry_after_delay

    base_s = _RATE_LIMIT_FALLBACK_BASE_S.get(settings.provider, 1.0)
    return base_s * (2 ** max(0, attempt - 1))


def _http_status_code(exc: Exception) -> int | None:
    if not isinstance(exc, requests.HTTPError):
        return None
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return int(status_code) if isinstance(status_code, int) else None


def _response_headers(exc: Exception) -> dict[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _retry_after_delay_s(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
