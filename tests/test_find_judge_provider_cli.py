from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anydoc2md.judge_probe_runner import ProbeResult
from anydoc2md.settings import DEFAULT_OPENAI_JUDGE_URL


def test_main_cloud_provider_lists_models_without_probing(
    monkeypatch,
    capsys,
) -> None:
    from anydoc2md.find_judge import main

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")

    with patch("anydoc2md.find_judge.fetch_judge_model_ids", return_value=["gpt-test"]) as fetch:
        rc = main(
            [
                "--judge-provider",
                "openai",
                "--list-models-only",
            ]
        )

    assert rc == 0
    fetch.assert_called_once()
    config = fetch.call_args.args[0]
    assert config.provider == "openai"
    assert config.url == DEFAULT_OPENAI_JUDGE_URL
    assert config.api_key == "sk-test"
    out = capsys.readouterr().out
    assert "Judge provider: openai" in out
    assert "gpt-test" in out


def test_main_cloud_provider_passes_provider_settings_to_probes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from anydoc2md.find_judge import main

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: list[tuple[str, str]] = []

    def fake_probe_one_model(**kwargs):
        seen.append((kwargs["judge_provider"], kwargs["judge_api_key"]))
        model = kwargs["model"]
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=0.01,
            tokens_used=10,
            violations_count=7,
            passed=True,
            reason="ok",
        )

    def fake_probe_freeform_model(**kwargs):
        seen.append((kwargs["judge_provider"], kwargs["judge_api_key"]))
        model = kwargs["model"]
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=0.01,
            tokens_used=12,
            violations_count=6,
            passed=True,
            reason="ok",
        )

    with (
        patch("anydoc2md.find_judge.fetch_judge_model_ids", return_value=["gpt-test"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
        patch("anydoc2md.find_judge.probe_freeform_model", side_effect=fake_probe_freeform_model),
    ):
        rc = main(
            [
                "--judge-provider",
                "openai",
                "--model-name",
                "gpt-test",
                "--repeats",
                "1",
                "--artifacts-dir",
                str(tmp_path),
            ]
        )

    assert rc == 0
    assert seen == [("openai", "sk-test"), ("openai", "sk-test")]
