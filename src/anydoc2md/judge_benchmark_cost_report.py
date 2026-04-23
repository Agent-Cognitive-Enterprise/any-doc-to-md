"""CLI for estimating cloud judge benchmark costs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from anydoc2md.judge_benchmark_cost import (
    custom_model_price,
    estimate_benchmark_cost,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate provider token cost from judge_pdf_concurrency_benchmark JSON. "
            "Pricing is dated because provider prices can change."
        )
    )
    parser.add_argument("benchmark_json", type=Path, help="Benchmark JSON artifact.")
    parser.add_argument("--provider", default=None, help="Override provider in the JSON.")
    parser.add_argument("--model", default=None, help="Override model in the JSON.")
    parser.add_argument(
        "--input-price-per-mtok",
        default=None,
        help="Custom input price in USD per 1M tokens.",
    )
    parser.add_argument(
        "--output-price-per-mtok",
        default=None,
        help="Custom output price in USD per 1M tokens.",
    )
    parser.add_argument(
        "--priced-at",
        default=None,
        help="Price verification date for custom prices, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--price-source-url",
        default=None,
        help="Source URL for custom prices.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for the machine-readable cost report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        price = _custom_price_from_args(args)
        report = estimate_benchmark_cost(
            args.benchmark_json,
            provider=args.provider,
            model=args.model,
            price=price,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )
    _print_report(report.to_dict())
    return 0


def _custom_price_from_args(args: argparse.Namespace):
    custom_values = (
        args.input_price_per_mtok,
        args.output_price_per_mtok,
        args.priced_at,
        args.price_source_url,
    )
    if not any(custom_values):
        return None
    if not all(custom_values):
        raise ValueError(
            "custom pricing requires --input-price-per-mtok, "
            "--output-price-per-mtok, --priced-at, and --price-source-url"
        )
    provider = args.provider or ""
    model = args.model or ""
    if not provider or not model:
        raise ValueError("custom pricing requires --provider and --model")
    return custom_model_price(
        provider=provider,
        model=model,
        input_usd_per_mtok=args.input_price_per_mtok,
        output_usd_per_mtok=args.output_price_per_mtok,
        priced_at=args.priced_at,
        source_url=args.price_source_url,
    )


def _print_report(report: dict) -> None:
    print(
        "Cost estimate: "
        f"provider={report['provider']} "
        f"model={report['model']} "
        f"priced_at={report['priced_at']} "
        f"input_tokens={report['input_tokens']} "
        f"output_tokens={report['output_tokens']} "
        f"total_cost_usd=${report['total_cost_usd']:.6f}",
        flush=True,
    )
    print(f"Price source: {report['price_source_url']}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
