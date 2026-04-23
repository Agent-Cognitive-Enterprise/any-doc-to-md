"""Cost estimation helpers for judge benchmark JSON artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

OPENAI_PRICING_URL = "https://platform.openai.com/docs/models/gpt-4o-mini"
OPENAI_CODEX_PRICING_URL = "https://platform.openai.com/docs/models/gpt-5.1-codex"
OPENAI_CODEX_MINI_PRICING_URL = "https://platform.openai.com/docs/models/gpt-5.1-codex-mini"
ANTHROPIC_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
DEEPSEEK_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing-details-usd/"
PRICE_CHECKED_DATE = "2026-04-22"
OPENAI_PRICE_CHECKED_DATE = "2026-04-23"
DEEPSEEK_PRICE_CHECKED_DATE = "2026-04-23"
_ONE_MILLION = Decimal("1000000")
_USD_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class JudgeModelPrice:
    """Per-million-token pricing metadata for a judge model."""

    provider: str
    model_match: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    priced_at: str
    source_url: str
    notes: str = ""

    def matches(self, *, provider: str, model: str) -> bool:
        return (
            provider.strip().lower() == self.provider
            and model.strip().lower().startswith(self.model_match)
        )


@dataclass(frozen=True)
class JudgeBenchmarkCostReport:
    """Estimated provider cost for one benchmark artifact."""

    source_path: str
    provider: str
    model: str
    priced_at: str
    price_source_url: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    input_tokens: int
    output_tokens: int
    total_tokens_used: int
    attempt_count: int
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "provider": self.provider,
            "model": self.model,
            "priced_at": self.priced_at,
            "price_source_url": self.price_source_url,
            "input_usd_per_mtok": float(self.input_usd_per_mtok),
            "output_usd_per_mtok": float(self.output_usd_per_mtok),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens_used": self.total_tokens_used,
            "attempt_count": self.attempt_count,
            "input_cost_usd": float(self.input_cost_usd),
            "output_cost_usd": float(self.output_cost_usd),
            "total_cost_usd": float(self.total_cost_usd),
            "notes": self.notes,
        }


DEFAULT_JUDGE_MODEL_PRICES = (
    JudgeModelPrice(
        provider="claude",
        model_match="claude-haiku-4-5",
        input_usd_per_mtok=Decimal("1.00"),
        output_usd_per_mtok=Decimal("5.00"),
        priced_at=PRICE_CHECKED_DATE,
        source_url=ANTHROPIC_PRICING_URL,
        notes="Anthropic standard API token pricing; excludes dashboard rounding.",
    ),
    JudgeModelPrice(
        provider="openai",
        model_match="gpt-4o-mini",
        input_usd_per_mtok=Decimal("0.15"),
        output_usd_per_mtok=Decimal("0.60"),
        priced_at=OPENAI_PRICE_CHECKED_DATE,
        source_url=OPENAI_PRICING_URL,
        notes="OpenAI standard API token pricing; excludes Batch discounts.",
    ),
    JudgeModelPrice(
        provider="openai",
        model_match="gpt-5.1-codex-mini",
        input_usd_per_mtok=Decimal("0.25"),
        output_usd_per_mtok=Decimal("2.00"),
        priced_at=OPENAI_PRICE_CHECKED_DATE,
        source_url=OPENAI_CODEX_MINI_PRICING_URL,
        notes="OpenAI standard API token pricing; excludes Batch discounts.",
    ),
    JudgeModelPrice(
        provider="openai",
        model_match="gpt-5.1-codex",
        input_usd_per_mtok=Decimal("1.25"),
        output_usd_per_mtok=Decimal("10.00"),
        priced_at=OPENAI_PRICE_CHECKED_DATE,
        source_url=OPENAI_CODEX_PRICING_URL,
        notes="OpenAI standard API token pricing; excludes Batch discounts.",
    ),
    JudgeModelPrice(
        provider="deepseek",
        model_match="deepseek-chat",
        input_usd_per_mtok=Decimal("0.27"),
        output_usd_per_mtok=Decimal("1.10"),
        priced_at=DEEPSEEK_PRICE_CHECKED_DATE,
        source_url=DEEPSEEK_PRICING_URL,
        notes=(
            "DeepSeek cache-miss input pricing for one-off requests; "
            "cache-hit pricing is lower but not assumed here."
        ),
    ),
)


def estimate_benchmark_cost(
    benchmark_path: Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    price: JudgeModelPrice | None = None,
) -> JudgeBenchmarkCostReport:
    payload = _read_json_object(benchmark_path)
    resolved_provider = provider or str(payload.get("judge_provider", ""))
    resolved_model = model or str(payload.get("judge_model", ""))
    if not resolved_provider:
        raise ValueError("benchmark JSON does not include judge_provider; pass --provider")
    if not resolved_model:
        raise ValueError("benchmark JSON does not include judge_model; pass --model")

    resolved_price = price or resolve_model_price(
        provider=resolved_provider,
        model=resolved_model,
    )
    token_usage = _token_usage(payload)
    input_cost = _token_cost(
        token_usage["input_tokens"],
        resolved_price.input_usd_per_mtok,
    )
    output_cost = _token_cost(
        token_usage["output_tokens"],
        resolved_price.output_usd_per_mtok,
    )
    return JudgeBenchmarkCostReport(
        source_path=str(benchmark_path),
        provider=resolved_provider,
        model=resolved_model,
        priced_at=resolved_price.priced_at,
        price_source_url=resolved_price.source_url,
        input_usd_per_mtok=resolved_price.input_usd_per_mtok,
        output_usd_per_mtok=resolved_price.output_usd_per_mtok,
        input_tokens=token_usage["input_tokens"],
        output_tokens=token_usage["output_tokens"],
        total_tokens_used=token_usage["total_tokens_used"],
        attempt_count=token_usage["attempt_count"],
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=(input_cost + output_cost).quantize(_USD_QUANT),
        notes=resolved_price.notes,
    )


def resolve_model_price(*, provider: str, model: str) -> JudgeModelPrice:
    for price in DEFAULT_JUDGE_MODEL_PRICES:
        if price.matches(provider=provider, model=model):
            return price
    raise ValueError(
        f"No built-in price for provider={provider!r} model={model!r}; "
        "pass explicit input/output prices."
    )


def custom_model_price(
    *,
    provider: str,
    model: str,
    input_usd_per_mtok: str,
    output_usd_per_mtok: str,
    priced_at: str,
    source_url: str,
) -> JudgeModelPrice:
    if not priced_at:
        raise ValueError("priced_at is required for custom prices")
    if not source_url:
        raise ValueError("source_url is required for custom prices")
    return JudgeModelPrice(
        provider=provider.strip().lower(),
        model_match=model.strip().lower(),
        input_usd_per_mtok=Decimal(input_usd_per_mtok),
        output_usd_per_mtok=Decimal(output_usd_per_mtok),
        priced_at=priced_at,
        source_url=source_url,
        notes="Custom price supplied by caller.",
    )


def _token_cost(tokens: int, usd_per_mtok: Decimal) -> Decimal:
    return ((Decimal(tokens) / _ONE_MILLION) * usd_per_mtok).quantize(
        _USD_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _token_usage(payload: dict[str, Any]) -> dict[str, int]:
    attempts = payload.get("attempts", [])
    if isinstance(attempts, list) and attempts:
        input_tokens = sum(_int_value(attempt.get("input_tokens", 0)) for attempt in attempts)
        output_tokens = sum(_int_value(attempt.get("output_tokens", 0)) for attempt in attempts)
        total_tokens = sum(_int_value(attempt.get("tokens_used", 0)) for attempt in attempts)
        if input_tokens or output_tokens:
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens_used": total_tokens or input_tokens + output_tokens,
                "attempt_count": len(attempts),
            }

    summary = payload.get("summary", [])
    if isinstance(summary, list) and summary:
        input_tokens = sum(_int_value(row.get("total_input_tokens", 0)) for row in summary)
        output_tokens = sum(_int_value(row.get("total_output_tokens", 0)) for row in summary)
        total_tokens = sum(_int_value(row.get("total_tokens_used", 0)) for row in summary)
        attempt_count = sum(_int_value(row.get("attempt_count", 0)) for row in summary)
        if input_tokens or output_tokens:
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens_used": total_tokens or input_tokens + output_tokens,
                "attempt_count": attempt_count,
            }

    raise ValueError(
        "benchmark JSON does not include split input/output token usage; "
        "rerun with the token-accounting benchmark code."
    )


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_json_object(path: Path) -> dict[str, Any]:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"benchmark JSON must be an object: {path}")
    return data
