from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anydoc2md.llm_judge import _call_lm_studio
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    DEFAULT_CLAUDE_JUDGE_URL,
    DEFAULT_DEEPSEEK_JUDGE_URL,
    DEFAULT_OPENAI_JUDGE_URL,
    ENV_CLAUDE_API_KEY,
    ENV_DEEPSEEK_API_KEY,
    ENV_JUDGE_MODEL,
    ENV_JUDGE_PROVIDER,
    ENV_JUDGE_URL,
    ENV_OPENAI_API_KEY,
    JUDGE_PROVIDER_CLAUDE,
    JUDGE_PROVIDER_DEEPSEEK,
    JUDGE_PROVIDER_LM_STUDIO,
    JUDGE_PROVIDER_OPENAI,
    JudgeSettings,
    load_judge_settings_from_env,
)


def _response(payload: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = payload
    mock.raise_for_status = MagicMock()
    return mock


def _clear_judge_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        ENV_JUDGE_PROVIDER,
        ENV_JUDGE_URL,
        ENV_JUDGE_MODEL,
        ENV_OPENAI_API_KEY,
        ENV_DEEPSEEK_API_KEY,
        ENV_CLAUDE_API_KEY,
    ):
        monkeypatch.delenv(name, raising=False)


def test_local_judge_env_keeps_existing_url_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_judge_env(monkeypatch)
    monkeypatch.setenv(ENV_JUDGE_MODEL, "qwen/test-model")

    with pytest.raises(AnyDocToMdConfigError) as exc_info:
        load_judge_settings_from_env()

    assert ENV_JUDGE_URL in str(exc_info.value)


def test_openai_judge_env_uses_openai_api_key_and_default_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_judge_env(monkeypatch)
    monkeypatch.setenv(ENV_JUDGE_PROVIDER, JUDGE_PROVIDER_OPENAI)
    monkeypatch.setenv(ENV_JUDGE_MODEL, "gpt-test")
    monkeypatch.setenv(ENV_OPENAI_API_KEY, "sk-openai-test")

    settings = load_judge_settings_from_env()

    assert settings.provider == JUDGE_PROVIDER_OPENAI
    assert settings.url == DEFAULT_OPENAI_JUDGE_URL
    assert settings.api_key == "sk-openai-test"


def test_deepseek_judge_env_uses_deepseek_api_key_and_default_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_judge_env(monkeypatch)
    monkeypatch.setenv(ENV_JUDGE_PROVIDER, JUDGE_PROVIDER_DEEPSEEK)
    monkeypatch.setenv(ENV_JUDGE_MODEL, "deepseek-chat")
    monkeypatch.setenv(ENV_DEEPSEEK_API_KEY, "sk-deepseek-test")

    settings = load_judge_settings_from_env()

    assert settings.provider == JUDGE_PROVIDER_DEEPSEEK
    assert settings.url == DEFAULT_DEEPSEEK_JUDGE_URL
    assert settings.api_key == "sk-deepseek-test"


def test_claude_judge_env_uses_claude_api_key_and_default_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_judge_env(monkeypatch)
    monkeypatch.setenv(ENV_JUDGE_PROVIDER, "anthropic")
    monkeypatch.setenv(ENV_JUDGE_MODEL, "claude-test")
    monkeypatch.setenv(ENV_CLAUDE_API_KEY, "sk-claude-test")

    settings = load_judge_settings_from_env()

    assert settings.provider == JUDGE_PROVIDER_CLAUDE
    assert settings.url == DEFAULT_CLAUDE_JUDGE_URL
    assert settings.api_key == "sk-claude-test"


def test_cloud_provider_requires_matching_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_judge_env(monkeypatch)
    monkeypatch.setenv(ENV_JUDGE_PROVIDER, JUDGE_PROVIDER_OPENAI)
    monkeypatch.setenv(ENV_JUDGE_MODEL, "gpt-test")

    with pytest.raises(AnyDocToMdConfigError) as exc_info:
        load_judge_settings_from_env()

    assert ENV_OPENAI_API_KEY in str(exc_info.value)


def test_invalid_judge_provider_raises() -> None:
    with pytest.raises(AnyDocToMdConfigError):
        JudgeSettings(
            url="http://localhost:1234/v1",
            model="test-model",
            provider="unknown",
        )


def test_local_request_uses_lm_studio_thinking_hint_without_auth() -> None:
    settings = JudgeSettings(
        url="http://localhost:1234/v1",
        model="qwen/test-model",
        provider=JUDGE_PROVIDER_LM_STUDIO,
    )
    response = _response(
        {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
    )

    with patch("anydoc2md.llm_judge.requests") as mock_requests:
        mock_requests.post.return_value = response
        result = _call_lm_studio("sys", "user", settings)
        text, tokens = result

    _, kwargs = mock_requests.post.call_args
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert kwargs["json"]["chat_template_kwargs"] == {"thinking": False}
    assert text == '{"ok": true}'
    assert tokens == 7
    assert result.input_tokens == 5
    assert result.output_tokens == 2


def test_openai_compatible_request_uses_bearer_auth_without_lm_studio_hint() -> None:
    settings = JudgeSettings(
        url=DEFAULT_OPENAI_JUDGE_URL,
        model="gpt-test",
        provider=JUDGE_PROVIDER_OPENAI,
        api_key="sk-openai-test",
    )
    response = _response(
        {
            "choices": [{"message": {"content": [{"text": '{"ok": true}'}]}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        }
    )

    with patch("anydoc2md.llm_judge.requests") as mock_requests:
        mock_requests.post.return_value = response
        result = _call_lm_studio("sys", "user", settings)
        text, tokens = result

    url, kwargs = mock_requests.post.call_args
    assert url[0] == "https://api.openai.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-openai-test"
    assert "chat_template_kwargs" not in kwargs["json"]
    assert text == '{"ok": true}'
    assert tokens == 9
    assert result.input_tokens == 7
    assert result.output_tokens == 2


def test_claude_request_uses_messages_api_headers_and_token_sum() -> None:
    settings = JudgeSettings(
        url="https://api.anthropic.com/v1",
        model="claude-test",
        provider=JUDGE_PROVIDER_CLAUDE,
        api_key="sk-claude-test",
    )
    response = _response(
        {
            "content": [{"type": "text", "text": '{"ok": true}'}],
            "usage": {"input_tokens": 11, "output_tokens": 5},
        }
    )

    with patch("anydoc2md.llm_judge.requests") as mock_requests:
        mock_requests.post.return_value = response
        result = _call_lm_studio("sys", "user", settings)
        text, tokens = result

    url, kwargs = mock_requests.post.call_args
    assert url[0] == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "sk-claude-test"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"]["system"] == "sys"
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "user"}]
    assert text == '{"ok": true}'
    assert tokens == 16
    assert result.input_tokens == 11
    assert result.output_tokens == 5
