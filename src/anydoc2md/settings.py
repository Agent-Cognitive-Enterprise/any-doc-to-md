"""Configuration helpers for host applications using `anydoc2md`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

ENV_JUDGE_PROVIDER = "ANYDOC2MD_JUDGE_PROVIDER"
ENV_JUDGE_URL = "ANYDOC2MD_JUDGE_URL"
ENV_JUDGE_MODEL = "ANYDOC2MD_JUDGE_MODEL"
ENV_JUDGE_TIMEOUT_S = "ANYDOC2MD_JUDGE_TIMEOUT_S"
ENV_JUDGE_MAX_TOKENS = "ANYDOC2MD_JUDGE_MAX_TOKENS"
ENV_JUDGE_DISABLE_THINKING = "ANYDOC2MD_JUDGE_DISABLE_THINKING"
ENV_JUDGE_TEMPERATURE = "ANYDOC2MD_JUDGE_TEMPERATURE"
ENV_JUDGE_PDF_CONCURRENCY = "ANYDOC2MD_JUDGE_PDF_CONCURRENCY"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
ENV_CLAUDE_API_KEY = "CLAUDE_API_KEY"

JUDGE_PROVIDER_LM_STUDIO = "lm_studio"
JUDGE_PROVIDER_OPENAI = "openai"
JUDGE_PROVIDER_DEEPSEEK = "deepseek"
JUDGE_PROVIDER_CLAUDE = "claude"
VALID_JUDGE_PROVIDERS = frozenset(
    {
        JUDGE_PROVIDER_LM_STUDIO,
        JUDGE_PROVIDER_OPENAI,
        JUDGE_PROVIDER_DEEPSEEK,
        JUDGE_PROVIDER_CLAUDE,
    }
)
_JUDGE_PROVIDER_ALIASES = {
    "local": JUDGE_PROVIDER_LM_STUDIO,
    "lm-studio": JUDGE_PROVIDER_LM_STUDIO,
    "lmstudio": JUDGE_PROVIDER_LM_STUDIO,
    "anthropic": JUDGE_PROVIDER_CLAUDE,
}

AUDIT_MODE_AUTO = "auto"
AUDIT_MODE_LIGHT = "light"
VALID_AUDIT_MODES = frozenset({AUDIT_MODE_AUTO, AUDIT_MODE_LIGHT})

DEFAULT_JUDGE_TIMEOUT_S = 90
DEFAULT_JUDGE_MAX_TOKENS = 4096
DEFAULT_JUDGE_DISABLE_THINKING = True
DEFAULT_JUDGE_TEMPERATURE = 0.1
DEFAULT_JUDGE_PDF_CONCURRENCY = 4
DEFAULT_JUDGE_PROVIDER = JUDGE_PROVIDER_LM_STUDIO
DEFAULT_OPENAI_JUDGE_URL = "https://api.openai.com/v1"
DEFAULT_DEEPSEEK_JUDGE_URL = "https://api.deepseek.com/v1"
DEFAULT_CLAUDE_JUDGE_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_CLAUDE_ANTHROPIC_VERSION = "2023-06-01"


class AnyDocToMdConfigError(ValueError):
    """Raised when required `anydoc2md` configuration is missing or invalid."""


@dataclass(frozen=True)
class JudgeSettings:
    """Runtime settings for the near-tie LLM judge."""

    url: str
    model: str
    provider: str = DEFAULT_JUDGE_PROVIDER
    api_key: str = field(default="", repr=False)
    timeout_s: int = DEFAULT_JUDGE_TIMEOUT_S
    max_tokens: int = DEFAULT_JUDGE_MAX_TOKENS
    disable_thinking: bool = DEFAULT_JUDGE_DISABLE_THINKING
    temperature: float = DEFAULT_JUDGE_TEMPERATURE
    pdf_concurrency: int = DEFAULT_JUDGE_PDF_CONCURRENCY
    anthropic_version: str = DEFAULT_CLAUDE_ANTHROPIC_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", normalize_judge_provider(self.provider))
        if self.pdf_concurrency < 1:
            raise AnyDocToMdConfigError(
                f"pdf_concurrency must be a positive integer; got {self.pdf_concurrency!r}"
            )


def normalize_audit_mode(value: str) -> str:
    """Validate and normalize a requested tournament audit mode."""
    normalized = value.strip().lower()
    if normalized not in VALID_AUDIT_MODES:
        valid = ", ".join(sorted(VALID_AUDIT_MODES))
        raise AnyDocToMdConfigError(
            f"Unsupported anydoc2md audit mode {value!r}; expected one of: {valid}"
        )
    return normalized


def normalize_judge_provider(value: str) -> str:
    """Validate and normalize a requested judge provider."""
    normalized = value.strip().lower().replace(" ", "_")
    normalized = _JUDGE_PROVIDER_ALIASES.get(normalized, normalized)
    if normalized not in VALID_JUDGE_PROVIDERS:
        valid = ", ".join(sorted(VALID_JUDGE_PROVIDERS))
        raise AnyDocToMdConfigError(
            f"Unsupported anydoc2md judge provider {value!r}; expected one of: {valid}"
        )
    return normalized


def load_judge_settings_from_env() -> JudgeSettings:
    """Read judge settings from environment variables."""
    provider = normalize_judge_provider(
        os.getenv(ENV_JUDGE_PROVIDER, DEFAULT_JUDGE_PROVIDER)
    )
    url = os.getenv(ENV_JUDGE_URL, "").strip()
    model = os.getenv(ENV_JUDGE_MODEL, "").strip()
    api_key = _provider_api_key(provider)

    missing: list[str] = []
    if not url and provider == JUDGE_PROVIDER_LM_STUDIO:
        missing.append(ENV_JUDGE_URL)
    if not model:
        missing.append(ENV_JUDGE_MODEL)
    if provider != JUDGE_PROVIDER_LM_STUDIO and not api_key:
        missing.append(_provider_api_key_env(provider))
    if missing:
        joined = ", ".join(missing)
        raise AnyDocToMdConfigError(
            f"Missing required anydoc2md judge env vars: {joined}"
        )

    if not url:
        url = _default_provider_url(provider)

    return JudgeSettings(
        url=url,
        model=model,
        provider=provider,
        api_key=api_key,
        timeout_s=_env_int(ENV_JUDGE_TIMEOUT_S, DEFAULT_JUDGE_TIMEOUT_S),
        max_tokens=_env_int(ENV_JUDGE_MAX_TOKENS, DEFAULT_JUDGE_MAX_TOKENS),
        disable_thinking=_env_bool(
            ENV_JUDGE_DISABLE_THINKING,
            DEFAULT_JUDGE_DISABLE_THINKING,
        ),
        temperature=_env_float(ENV_JUDGE_TEMPERATURE, DEFAULT_JUDGE_TEMPERATURE),
        pdf_concurrency=_env_positive_int(
            ENV_JUDGE_PDF_CONCURRENCY,
            DEFAULT_JUDGE_PDF_CONCURRENCY,
        ),
    )


def _default_provider_url(provider: str) -> str:
    if provider == JUDGE_PROVIDER_OPENAI:
        return DEFAULT_OPENAI_JUDGE_URL
    if provider == JUDGE_PROVIDER_DEEPSEEK:
        return DEFAULT_DEEPSEEK_JUDGE_URL
    if provider == JUDGE_PROVIDER_CLAUDE:
        return DEFAULT_CLAUDE_JUDGE_URL
    return ""


def _provider_api_key(provider: str) -> str:
    env_var = _provider_api_key_env(provider)
    if not env_var:
        return ""
    return os.getenv(env_var, "").strip()


def _provider_api_key_env(provider: str) -> str:
    if provider == JUDGE_PROVIDER_OPENAI:
        return ENV_OPENAI_API_KEY
    if provider == JUDGE_PROVIDER_DEEPSEEK:
        return ENV_DEEPSEEK_API_KEY
    if provider == JUDGE_PROVIDER_CLAUDE:
        return ENV_CLAUDE_API_KEY
    return ""


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


def _env_positive_int(name: str, default: int) -> int:
    value = _env_int(name, default)
    if value < 1:
        raise AnyDocToMdConfigError(
            f"{name} must be a positive integer; got {value!r}"
        )
    return value
