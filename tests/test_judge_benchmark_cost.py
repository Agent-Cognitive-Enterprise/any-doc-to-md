from __future__ import annotations

import json
from pathlib import Path

from anydoc2md.judge_benchmark_cost import (
    PRICE_CHECKED_DATE,
    custom_model_price,
    estimate_benchmark_cost,
)
from anydoc2md.judge_benchmark_cost_report import main


def _write_benchmark(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_estimates_known_claude_benchmark_cost(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    _write_benchmark(
        path,
        {
            "judge_provider": "claude",
            "judge_model": "claude-haiku-4-5-20251001",
            "attempts": [
                {"input_tokens": 1000, "output_tokens": 200, "tokens_used": 1200},
                {"input_tokens": 500, "output_tokens": 100, "tokens_used": 600},
            ],
        },
    )

    report = estimate_benchmark_cost(path)

    assert report.input_tokens == 1500
    assert report.output_tokens == 300
    assert report.priced_at == PRICE_CHECKED_DATE
    assert report.total_cost_usd == report.input_cost_usd + report.output_cost_usd
    assert float(report.total_cost_usd) == 0.003


def test_estimates_openai_cost_from_summary_when_attempts_absent(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    _write_benchmark(
        path,
        {
            "judge_provider": "openai",
            "judge_model": "gpt-4o-mini",
            "summary": [
                {
                    "attempt_count": 2,
                    "total_input_tokens": 100000,
                    "total_output_tokens": 50000,
                    "total_tokens_used": 150000,
                }
            ],
        },
    )

    report = estimate_benchmark_cost(path)

    assert report.attempt_count == 2
    assert float(report.total_cost_usd) == 0.045


def test_custom_price_requires_dated_source(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    _write_benchmark(
        path,
        {
            "judge_provider": "test",
            "judge_model": "model-a",
            "attempts": [{"input_tokens": 1000, "output_tokens": 1000}],
        },
    )

    report = estimate_benchmark_cost(
        path,
        price=custom_model_price(
            provider="test",
            model="model-a",
            input_usd_per_mtok="2.00",
            output_usd_per_mtok="4.00",
            priced_at="2026-04-22",
            source_url="https://example.test/pricing",
        ),
    )

    assert report.priced_at == "2026-04-22"
    assert report.price_source_url == "https://example.test/pricing"
    assert float(report.total_cost_usd) == 0.006


def test_cli_writes_cost_report_json(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    output = tmp_path / "cost.json"
    _write_benchmark(
        path,
        {
            "judge_provider": "openai",
            "judge_model": "gpt-4o-mini",
            "attempts": [{"input_tokens": 1000, "output_tokens": 1000}],
        },
    )

    rc = main([str(path), "--output-json", str(output)])

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["priced_at"] == PRICE_CHECKED_DATE
    assert payload["total_cost_usd"] == 0.00075
