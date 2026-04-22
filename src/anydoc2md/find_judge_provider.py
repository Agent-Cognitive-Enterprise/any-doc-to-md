"""Provider setup for the find_judge CLI."""

from __future__ import annotations

from dataclasses import dataclass
import os

from anydoc2md.judge_probe_models import fetch_model_ids, model_listing_url
from anydoc2md.settings import (
    DEFAULT_CLAUDE_ANTHROPIC_VERSION,
    DEFAULT_JUDGE_PROVIDER,
    ENV_JUDGE_PROVIDER,
    ENV_JUDGE_URL,
    JUDGE_PROVIDER_LM_STUDIO,
    default_judge_url_for_provider,
    judge_api_key_env_for_provider,
    judge_api_key_from_env,
    normalize_judge_provider,
)


@dataclass(frozen=True)
class JudgeProviderConfig:
    provider: str
    url: str
    api_key: str
    anthropic_version: str = DEFAULT_CLAUDE_ANTHROPIC_VERSION


def resolve_judge_provider_config(
    *,
    provider_arg: str | None,
    url_arg: str | None,
) -> JudgeProviderConfig:
    provider = normalize_judge_provider(
        provider_arg or os.getenv(ENV_JUDGE_PROVIDER, DEFAULT_JUDGE_PROVIDER)
    )
    explicit_url = (url_arg or "").strip()
    env_url = os.getenv(ENV_JUDGE_URL, "").strip()
    if explicit_url:
        url = explicit_url
    elif provider == JUDGE_PROVIDER_LM_STUDIO:
        url = env_url
    else:
        url = default_judge_url_for_provider(provider)
    api_key = judge_api_key_from_env(provider)

    if provider == JUDGE_PROVIDER_LM_STUDIO and not url:
        raise ValueError(f"--judge-url or {ENV_JUDGE_URL} is required for lm_studio.")
    if provider != JUDGE_PROVIDER_LM_STUDIO and not api_key:
        env_var = judge_api_key_env_for_provider(provider)
        raise ValueError(f"{env_var} is required for {provider}.")

    return JudgeProviderConfig(provider=provider, url=url, api_key=api_key)


def fetch_judge_model_ids(config: JudgeProviderConfig) -> list[str]:
    return fetch_model_ids(
        config.url,
        provider=config.provider,
        api_key=config.api_key,
        anthropic_version=config.anthropic_version,
    )


def judge_model_listing_url(config: JudgeProviderConfig) -> str:
    return model_listing_url(config.url, provider=config.provider)
