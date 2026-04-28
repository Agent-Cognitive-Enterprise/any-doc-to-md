"""User-facing command line interface for ADTM."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.format_converters.tournament.runner import (
    available_adapter_names,
    default_adapter_names,
)
from anydoc2md.settings import AUDIT_MODE_LIGHT, VALID_AUDIT_MODES


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    if args.command == "convert":
        return _convert(args)
    if args.command == "adapters":
        return _adapters(args)

    parser.print_help()
    return 2


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anydoc2md",
        description="Convert documents to Markdown with ADTM.",
    )
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser(
        "convert",
        help="convert one source document to a Markdown output directory",
    )
    convert.add_argument("source", type=Path, help="Source document path.")
    convert.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for index.md, images/, and anydoc2md-result.json.",
    )
    convert.add_argument(
        "--staging-dir",
        type=Path,
        default=None,
        help="Optional tournament staging directory. Defaults under output dir.",
    )
    convert.add_argument(
        "--adapter",
        action="append",
        dest="adapters",
        default=None,
        choices=available_adapter_names(),
        help="Adapter to run. Repeat to run several. Default: inhouse.",
    )
    convert.add_argument(
        "--all-adapters",
        action="store_true",
        help="Run every implemented adapter. Optional external tools may be required.",
    )
    convert.add_argument(
        "--audit-mode",
        choices=sorted(VALID_AUDIT_MODES),
        default=AUDIT_MODE_LIGHT,
        help="Audit mode. Default: light, no LLM judge required.",
    )
    convert.add_argument(
        "--timeout-s",
        type=int,
        default=600,
        help="Per-adapter timeout in seconds. Default: 600.",
    )
    convert.add_argument(
        "--json",
        action="store_true",
        help="Print the full tournament result as JSON.",
    )

    adapters = subparsers.add_parser(
        "adapters",
        help="list available and default adapters",
    )
    adapters.add_argument(
        "--json",
        action="store_true",
        help="Print adapter information as JSON.",
    )
    return parser


def _convert(args: argparse.Namespace) -> int:
    source = args.source
    output_dir = args.output_dir
    if not source.is_file():
        print(f"Error: source file not found: {source}", file=sys.stderr)
        return 2
    if args.timeout_s <= 0:
        print("Error: --timeout-s must be > 0.", file=sys.stderr)
        return 2

    adapters = _adapter_selection(args)
    staging_dir = args.staging_dir or (output_dir / ".any-doc-to-md" / "staging")
    result = run_full_tournament(
        source,
        staging_dir,
        adapters=adapters,
        audit_mode=args.audit_mode,
        timeout_s=args.timeout_s,
    )
    _write_result_json(output_dir, result.to_dict())

    if result.winner_staging_dir is None:
        _print_result(args, result.to_dict())
        print(f"Error: no winning conversion for {source}", file=sys.stderr)
        return 1

    _publish_winner(result.winner_staging_dir, output_dir)
    _print_result(args, result.to_dict())
    if not args.json:
        print(f"winner={result.winner} output={output_dir / 'index.md'}")
    return 0


def _adapters(args: argparse.Namespace) -> int:
    payload = {
        "default": default_adapter_names(),
        "available": available_adapter_names(),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Default adapters: " + ", ".join(payload["default"]))
        print("Available adapters: " + ", ".join(payload["available"]))
    return 0


def _adapter_selection(args: argparse.Namespace) -> list[str] | None:
    if args.all_adapters:
        return available_adapter_names()
    if args.adapters:
        return list(args.adapters)
    return None


def _write_result_json(output_dir: Path, payload: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "anydoc2md-result.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _publish_winner(winner_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_src = winner_dir / "index.md"
    if markdown_src.exists():
        shutil.copy2(markdown_src, output_dir / "index.md")

    images_src = winner_dir / "images"
    images_dst = output_dir / "images"
    if images_dst.exists():
        shutil.rmtree(images_dst)
    if images_src.is_dir():
        shutil.copytree(images_src, images_dst)


def _print_result(args: argparse.Namespace, payload: dict) -> None:
    if args.json:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
