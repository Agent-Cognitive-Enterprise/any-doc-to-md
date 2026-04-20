"""Configuration helpers for host applications using `anydoc2md`."""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_JUDGE_URL = "ANYDOC2MD_JUDGE_URL"
ENV_JUDGE_MODEL = "ANYDOC2MD_JUDGE_MODEL"
ENV_JUDGE_TIMEOUT_S = "ANYDOC2MD_JUDGE_TIMEOUT_S"
ENV_JUDGE_MAX_TOKENS = "ANYDOC2MD_JUDGE_MAX_TOKENS"
ENV_JUDGE_DISABLE_THINKING = "ANYDOC2MD_JUDGE_DISABLE_THINKING"
ENV_JUDGE_TEMPERATURE = "ANYDOC2MD_JUDGE_TEMPERATURE"

DEFAULT_JUDGE_TIMEOUT_S = 90
DEFAULT_JUDGE_MAX_TOKENS = 4096
DEFAULT_JUDGE_DISABLE_THINKING = True
DEFAULT_JUDGE_TEMPERATURE = 0.1


class AnyDocToMdConfigError(ValueError):
    """Raised when required `anydoc2md` configuration is missing or invalid."""


@dataclass(frozen=True)
class JudgeSettings:
    """Runtime settings for the near-tie LLM judge."""

    url: str
    model: str
    timeout_s: int = DEFAULT_JUDGE_TIMEOUT_S
    max_tokens: int = DEFAULT_JUDGE_MAX_TOKENS
    disable_thinking: bool = DEFAULT_JUDGE_DISABLE_THINKING
    temperature: float = DEFAULT_JUDGE_TEMPERATURE


def load_judge_settings_from_env() -> JudgeSettings:
    """Read judge settings from environment variables."""
    url = os.getenv(ENV_JUDGE_URL, "").strip()
    model = os.getenv(ENV_JUDGE_MODEL, "").strip()

    missing: list[str] = []
    if not url:
        missing.append(ENV_JUDGE_URL)
    if not model:
        missing.append(ENV_JUDGE_MODEL)
    if missing:
        joined = ", ".join(missing)
        raise AnyDocToMdConfigError(
            f"Missing required anydoc2md judge env vars: {joined}"
        )

    return JudgeSettings(
        url=url,
        model=model,
        timeout_s=_env_int(ENV_JUDGE_TIMEOUT_S, DEFAULT_JUDGE_TIMEOUT_S),
        max_tokens=_env_int(ENV_JUDGE_MAX_TOKENS, DEFAULT_JUDGE_MAX_TOKENS),
        disable_thinking=_env_bool(
            ENV_JUDGE_DISABLE_THINKING,
            DEFAULT_JUDGE_DISABLE_THINKING,
        ),
        temperature=_env_float(ENV_JUDGE_TEMPERATURE, DEFAULT_JUDGE_TEMPERATURE),
    )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise AnyDocToMdConfigError(
            f"{name} must be an integer; got {value!r}"
        ) from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise AnyDocToMdConfigError(
            f"{name} must be a float; got {value!r}"
        ) from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise AnyDocToMdConfigError(
        f"{name} must be a boolean string; got {value!r}"
    )
