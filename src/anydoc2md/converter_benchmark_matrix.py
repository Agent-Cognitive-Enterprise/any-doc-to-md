"""Aggregate converter tournament artifacts into a user-facing benchmark matrix."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any


PAGE_BUCKETS = (
    ("1 page", 1),
    ("2-10 pages", 10),
    ("11-50 pages", 50),
    ("51-100 pages", 100),
    ("101-1000 pages", 1000),
)
OPTIONAL_MIN_MEDIAN_TIME_S = 30.0
OPTIONAL_MIN_TOTAL_TIME_S = 120.0
OPTIONAL_MAX_PAGES_PER_SECOND = 1.0
HIGH_MIN_GATE_PASS_RATE = 0.95
MEDIUM_MIN_GATE_PASS_RATE = 0.80
LOW_MIN_GATE_PASS_RATE = 0.50


@dataclass(frozen=True)
class AdapterObservation:
    """One adapter's observed conversion outcome for one source document."""

    document_id: str
    bucket: str
    page_count: int
    adapter: str
    status: str
    timing_ms: int
    markdown_chars: int
    score: float | None
    disqualified_reason: str
    won: bool

    @property
    def raw_success(self) -> bool:
        return self.status == "ok" and self.markdown_chars > 0

    @property
    def gate_passed(self) -> bool:
        return self.score is not None


def build_converter_benchmark_matrix(
    staging_root: Path,
    *,
    sources_dir: Path | None = None,
    measured_at: str = "",
    hardware_label: str = "",
) -> dict[str, Any]:
    """Build a benchmark matrix from a completed tournament staging root."""
    reports = [_load_document_report(path, sources_dir) for path in _report_paths(staging_root)]
    observations = [
        observation
        for report in reports
        for observation in _adapter_observations(report)
    ]
    return {
        "staging_root": str(staging_root),
        "sources_dir": str(sources_dir) if sources_dir else "",
        "measured_at": measured_at,
        "hardware_label": hardware_label,
        "bucket_definitions": _bucket_definitions(),
        "document_count": len(reports),
        "documents": [_document_summary(report) for report in reports],
        "bucket_adapter_summary": _summaries(observations, key_fields=("bucket", "adapter")),
        "adapter_summary": _summaries(observations, key_fields=("adapter",)),
    }


def render_markdown_matrix(matrix: dict[str, Any]) -> str:
    """Render the benchmark matrix as compact Markdown tables."""
    lines = [
        "# ADTM Converter Benchmark Matrix",
        "",
        f"- measured_at: `{matrix.get('measured_at', '')}`",
        f"- hardware: `{matrix.get('hardware_label', '')}`",
        f"- staging_root: `{matrix.get('staging_root', '')}`",
        f"- documents: `{matrix.get('document_count', 0)}`",
        "- cloud_cost_usd: `$0` for this light-mode converter run",
        "",
        "## By Page Bucket And Adapter",
        "",
    ]
    lines.extend(_markdown_table(matrix.get("bucket_adapter_summary", [])))
    lines.extend(["", "## Adapter Totals", ""])
    lines.extend(_markdown_table(matrix.get("adapter_summary", [])))
    lines.extend(["", "## Documents", ""])
    lines.extend(_markdown_table(matrix.get("documents", [])))
    lines.append("")
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate ADTM tournament qa_report.json artifacts into a speed/quality matrix."
    )
    parser.add_argument("staging_root", type=Path, help="Tournament staging root.")
    parser.add_argument("--sources-dir", type=Path, default=None, help="Optional source corpus root.")
    parser.add_argument("--measured-at", default="", help="Measurement date/time label.")
    parser.add_argument("--hardware", default="", help="Hardware/runtime label for the run.")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--output-md", type=Path, default=None, help="Optional Markdown output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    matrix = build_converter_benchmark_matrix(
        args.staging_root,
        sources_dir=args.sources_dir,
        measured_at=args.measured_at,
        hardware_label=args.hardware,
    )
    markdown = render_markdown_matrix(matrix)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(markdown, encoding="utf-8")
    if not args.output_json and not args.output_md:
        print(markdown)
    return 0


def _report_paths(staging_root: Path) -> list[Path]:
    paths = sorted(staging_root.rglob("qa_report.json"))
    return [path for path in paths if _is_document_report(path)]


def _is_document_report(path: Path) -> bool:
    return path.parent.name == "winner" or (path.parent / "winner").is_dir() is False


def _load_document_report(path: Path, sources_dir: Path | None) -> dict[str, Any]:
    payload = _read_json(path)
    doc_root = path.parent.parent if path.parent.name == "winner" else path.parent
    source_path = Path(str(payload.get("source_path", "")))
    page_count = _int(payload.get("traits", {}).get("page_count", 0))
    return {
        "payload": payload,
        "doc_root": doc_root,
        "document_id": _document_id(source_path, sources_dir),
        "page_count": page_count,
        "bucket": page_bucket(page_count),
    }


def page_bucket(page_count: int) -> str:
    if page_count <= 0:
        return "unknown pages"
    for label, upper in PAGE_BUCKETS:
        if page_count <= upper:
            return label
    return "1000+ pages"


def _adapter_observations(report: dict[str, Any]) -> list[AdapterObservation]:
    payload = report["payload"]
    score_by_adapter = {
        row["adapter_name"]: float(row["total_score"])
        for row in payload.get("selection", {}).get("ranked", [])
    }
    disqualified = payload.get("selection", {}).get("disqualified", {})
    winner = str(payload.get("winner") or "")
    observations: list[AdapterObservation] = []
    for result_path in sorted(report["doc_root"].glob("*/adapter_result.json")):
        if result_path.parent.name == "winner":
            continue
        result = _read_json(result_path)
        adapter = str(result.get("method_name") or result_path.parent.name)
        observations.append(
            AdapterObservation(
                document_id=report["document_id"],
                bucket=report["bucket"],
                page_count=report["page_count"],
                adapter=adapter,
                status=str(result.get("status", "")),
                timing_ms=_int(result.get("timing_ms", 0)),
                markdown_chars=_int(result.get("markdown_chars", 0)),
                score=score_by_adapter.get(adapter),
                disqualified_reason=str(disqualified.get(adapter, "")),
                won=adapter == winner,
            )
        )
    return observations


def _summaries(
    observations: list[AdapterObservation],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[AdapterObservation]] = {}
    for observation in observations:
        key = tuple(str(getattr(observation, field)) for field in key_fields)
        grouped.setdefault(key, []).append(observation)

    rows: list[dict[str, Any]] = []
    for key, items in grouped.items():
        row = dict(zip(key_fields, key, strict=True))
        scores = [item.score for item in items if item.score is not None]
        timings = [item.timing_ms for item in items if item.timing_ms > 0]
        total_pages = sum(item.page_count for item in items if item.page_count > 0)
        total_timing_ms = sum(timings)
        total_time_s = _seconds(total_timing_ms) if timings else None
        median_time_s = _seconds(median(timings)) if timings else None
        pages_per_second = _pages_per_second(total_pages, total_timing_ms)
        raw_successes = sum(1 for item in items if item.raw_success)
        gate_passes = sum(1 for item in items if item.gate_passed)
        wins = sum(1 for item in items if item.won)
        raw_success_rate = _rate(raw_successes, len(items))
        gate_pass_rate = _rate(gate_passes, len(items))
        mean_score = mean(scores) if scores else None
        row.update(
            {
                "attempts": len(items),
                "total_pages": total_pages,
                "total_time_s": total_time_s,
                "raw_successes": raw_successes,
                "gate_passes": gate_passes,
                "wins": wins,
                "raw_success_rate": raw_success_rate,
                "gate_pass_rate": gate_pass_rate,
                "win_rate": _rate(wins, len(items)),
                "mean_time_s": _seconds(mean(timings)) if timings else None,
                "median_time_s": median_time_s,
                "pages_per_second": pages_per_second,
                "mean_score": round(mean_score, 3) if mean_score is not None else None,
                "quality_tier": quality_tier(mean_score, gate_pass_rate=gate_pass_rate),
                "default_set_signal": default_set_signal(
                    raw_successes=raw_successes,
                    wins=wins,
                    total_time_s=total_time_s,
                    median_time_s=median_time_s,
                    pages_per_second=pages_per_second,
                ),
                "cloud_cost_usd": 0.0,
            }
        )
        rows.append(row)
    return sorted(rows, key=_summary_sort_key)


def quality_tier(mean_score: float | None, *, gate_pass_rate: float = 1.0) -> str:
    """
    Return a user-facing quality tier from score and hard-gate eligibility.

    Lower scores are better, but a good score over only a tiny eligible subset
    should not be reported as high quality for the whole observed corpus.
    """
    if mean_score is None or gate_pass_rate <= 0:
        return "failed"
    if gate_pass_rate < LOW_MIN_GATE_PASS_RATE:
        return "poor"
    if mean_score <= 10:
        if gate_pass_rate >= HIGH_MIN_GATE_PASS_RATE:
            return "high"
        if gate_pass_rate >= MEDIUM_MIN_GATE_PASS_RATE:
            return "medium"
        return "low"
    if mean_score <= 50:
        if gate_pass_rate < MEDIUM_MIN_GATE_PASS_RATE:
            return "low"
        return "medium"
    if mean_score <= 100:
        return "low"
    return "poor"


def default_set_signal(
    *,
    raw_successes: int,
    wins: int,
    total_time_s: float | None,
    median_time_s: float | None,
    pages_per_second: float | None,
) -> str:
    """Return a conservative default-pool signal from observed tournament data."""
    if raw_successes == 0:
        return "not_available_or_unsupported"
    if wins > 0:
        return "keep_default_candidate"
    if _is_slow(
        total_time_s=total_time_s,
        median_time_s=median_time_s,
        pages_per_second=pages_per_second,
    ):
        return "move_to_optional_candidate"
    return "watch_no_wins"


def _is_slow(
    *,
    total_time_s: float | None,
    median_time_s: float | None,
    pages_per_second: float | None,
) -> bool:
    if total_time_s is not None and total_time_s >= OPTIONAL_MIN_TOTAL_TIME_S:
        return True
    if median_time_s is not None and median_time_s >= OPTIONAL_MIN_MEDIAN_TIME_S:
        return True
    return pages_per_second is not None and pages_per_second <= OPTIONAL_MAX_PAGES_PER_SECOND


def _document_summary(report: dict[str, Any]) -> dict[str, Any]:
    payload = report["payload"]
    traits = payload.get("traits", {})
    return {
        "document_id": report["document_id"],
        "bucket": report["bucket"],
        "file_type": str(traits.get("file_type", "")),
        "page_count": _int(traits.get("page_count", 0)),
        "word_count": _int(traits.get("word_count", 0)),
        "winner": str(payload.get("winner") or ""),
        "winner_score": payload.get("selection", {}).get("winner_score"),
        "adapter_count": len(payload.get("adapter_timing_ms", {})),
    }


def _markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    columns = list(rows[0])
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(row.get(column)) for column in columns) + " |")
    return lines


def _summary_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    bucket = str(row.get("bucket", ""))
    return (_bucket_sort_index(bucket), str(row.get("adapter", "")), json.dumps(row, sort_keys=True))


def _bucket_sort_index(bucket: str) -> int:
    labels = [label for label, _upper in PAGE_BUCKETS] + ["1000+ pages", "unknown pages"]
    try:
        return labels.index(bucket)
    except ValueError:
        return len(labels)


def _bucket_definitions() -> list[dict[str, Any]]:
    lower = 1
    definitions: list[dict[str, Any]] = []
    for label, upper in PAGE_BUCKETS:
        definitions.append({"label": label, "min_pages": lower, "max_pages": upper})
        lower = upper + 1
    definitions.append({"label": "1000+ pages", "min_pages": lower, "max_pages": None})
    definitions.append({"label": "unknown pages", "min_pages": None, "max_pages": None})
    return definitions


def _document_id(source_path: Path, sources_dir: Path | None) -> str:
    if sources_dir is not None:
        try:
            return source_path.resolve().relative_to(sources_dir.resolve()).as_posix()
        except ValueError:
            pass
    return source_path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 3)


def _seconds(milliseconds: float) -> float:
    return round(milliseconds / 1000, 3)


def _pages_per_second(page_count: int, timing_ms: int) -> float | None:
    if page_count <= 0 or timing_ms <= 0:
        return None
    return round(page_count / (timing_ms / 1000), 3)


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
