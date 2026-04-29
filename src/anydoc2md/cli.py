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
from anydoc2md.remediation_authoring import author_project_local_scaffolds
from anydoc2md.scaffold_staging import stage_project_scaffolds
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
        help=(
            "Output directory for this conversion. One directory per source document"
            " — re-running to the same path overwrites the previous result."
        ),
    )
    convert.add_argument(
        "--staging-dir",
        type=Path,
        default=None,
        help="Optional tournament staging directory. Defaults under output dir.",
    )
    convert.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help=(
            "Project root for shared ADTM state (.any-doc-to-md/ directory)."
            " Defaults to the current working directory."
            " Use this when converting multiple documents in one project so all"
            " findings and scaffolds are written to one location."
        ),
    )
    convert.add_argument(
        "--qa",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Project-wide QA extension (.py) applied to every document in this run."
            " When a per-document scaffold also exists both are merged and run together."
            " Mutually exclusive with --qa-all."
        ),
    )
    convert.add_argument(
        "--fix",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Project-wide fix extension (.py) applied to every adapter's output in this"
            " run. Merged with any per-document fix scaffold."
            " Mutually exclusive with --fix-all."
        ),
    )
    convert.add_argument(
        "--qa-all",
        action="store_true",
        help=(
            "Apply every QA extension in .any-doc-to-md/qa-extensions/ to this run,"
            " merged into a single combined check set."
            " Mutually exclusive with --qa."
        ),
    )
    convert.add_argument(
        "--fix-all",
        action="store_true",
        help=(
            "Apply every fix extension in .any-doc-to-md/fix-extensions/ to this run,"
            " merged into a single combined post-processing step."
            " Mutually exclusive with --fix."
        ),
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
    if args.qa and args.qa_all:
        print("Error: --qa and --qa-all are mutually exclusive.", file=sys.stderr)
        return 2
    if args.fix and args.fix_all:
        print("Error: --fix and --fix-all are mutually exclusive.", file=sys.stderr)
        return 2
    if args.qa is not None and not args.qa.is_file():
        print(f"Error: --qa file not found: {args.qa}", file=sys.stderr)
        return 2
    if args.fix is not None and not args.fix.is_file():
        print(f"Error: --fix file not found: {args.fix}", file=sys.stderr)
        return 2

    project_dir = args.project_dir or Path.cwd()
    anydoc2md_dir = project_dir / ".any-doc-to-md"
    adapters = _adapter_selection(args)
    staging_dir = args.staging_dir or (output_dir / ".any-doc-to-md" / "staging")
    stage_project_scaffolds(
        anydoc2md_dir, source, staging_dir,
        qa=args.qa,
        fix=args.fix,
        qa_all=args.qa_all,
        fix_all=args.fix_all,
    )
    result = run_full_tournament(
        source,
        staging_dir,
        adapters=adapters,
        audit_mode=args.audit_mode,
        timeout_s=args.timeout_s,
    )
    _write_result_json(output_dir, result.to_dict())
    _save_findings(anydoc2md_dir, source, result)

    if result.winner_staging_dir is None:
        _print_result(args, result.to_dict())
        print(f"Error: no winning conversion for {source}", file=sys.stderr)
        return 1

    _publish_winner(result.winner_staging_dir, output_dir)
    _print_result(args, result.to_dict())
    if not args.json:
        _print_adapter_table(result)
        print(f"winner={result.winner}  output={output_dir / 'index.md'}")
        if result.remediation_plan is not None:
            print(f"findings: {anydoc2md_dir / 'llm-findings' / source.name}.json")
            print(f"scaffolds: {anydoc2md_dir / 'qa-extensions'} and fix-extensions/")
            print("next steps: see docs/agent-conversion-guide.md")
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
    fixed_md = winner_dir / "index_fixed.md"
    markdown_src = fixed_md if fixed_md.exists() else winner_dir / "index.md"
    if markdown_src.exists():
        shutil.copy2(markdown_src, output_dir / "index.md")

    images_src = winner_dir / "images"
    images_dst = output_dir / "images"
    if images_dst.exists():
        shutil.rmtree(images_dst)
    if images_src.is_dir():
        shutil.copytree(images_src, images_dst)


def _save_findings(anydoc2md_dir: Path, source: Path, result) -> None:
    if result.judge_verdict is None and result.remediation_plan is None:
        return
    doc_key = source.name
    if result.judge_verdict is not None:
        findings_dir = anydoc2md_dir / "llm-findings"
        findings_dir.mkdir(parents=True, exist_ok=True)
        findings = {
            "doc_key": doc_key,
            "source_path": str(source),
            "judge_verdict": result.judge_verdict.to_dict(),
            "remediation_plan": (
                result.remediation_plan.to_dict() if result.remediation_plan else None
            ),
        }
        (findings_dir / f"{doc_key}.json").write_text(
            json.dumps(findings, indent=2, ensure_ascii=True), encoding="utf-8"
        )
    if result.remediation_plan is not None:
        author_project_local_scaffolds(
            report_data={"remediation_plan": result.remediation_plan.to_dict()},
            anydoc2md_dir=anydoc2md_dir,
            doc_key=doc_key,
        )


def _print_adapter_table(result) -> None:
    adapter_results = getattr(result, "adapter_results", None)
    selection = getattr(result, "selection", None)
    if not adapter_results or selection is None:
        return
    scores = {c.adapter_name: c.total_score for c in selection.ranked}
    disq = getattr(selection, "disqualified", {})
    name_w = max(len(r.method_name) for r in adapter_results)
    for r in adapter_results:
        n = r.method_name
        ms = f"{r.timing_ms}ms"
        if r.status == "timeout":
            score_s = "timeout"
        elif n in disq:
            score_s = "disq"
        elif n in scores:
            score_s = f"{scores[n]:.1f}"
        else:
            score_s = "error"
        mark = "  [winner]" if n == result.winner else ""
        print(f"  {n:<{name_w}}  {score_s:>7}  {ms:>8}{mark}")


def _print_result(args: argparse.Namespace, payload: dict) -> None:
    if args.json:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
