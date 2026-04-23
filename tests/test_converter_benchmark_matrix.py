from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from anydoc2md.converter_benchmark_matrix import (
    build_converter_benchmark_matrix,
    default_set_signal,
    main,
    page_bucket,
    quality_tier,
    render_markdown_matrix,
)


def test_page_bucket_matches_user_facing_size_breaks() -> None:
    assert page_bucket(1) == "1 page"
    assert page_bucket(10) == "2-10 pages"
    assert page_bucket(50) == "11-50 pages"
    assert page_bucket(100) == "51-100 pages"
    assert page_bucket(1000) == "101-1000 pages"
    assert page_bucket(0) == "unknown pages"


def test_quality_tier_uses_lower_score_as_better() -> None:
    assert quality_tier(None) == "failed"
    assert quality_tier(0) == "high"
    assert quality_tier(25) == "medium"
    assert quality_tier(75) == "low"
    assert quality_tier(125) == "poor"


def test_default_set_signal_marks_slow_no_win_adapters_optional() -> None:
    assert (
        default_set_signal(
            raw_successes=2,
            wins=0,
            total_time_s=90.0,
            median_time_s=45.0,
            pages_per_second=2.0,
        )
        == "move_to_optional_candidate"
    )
    assert (
        default_set_signal(
            raw_successes=2,
            wins=0,
            total_time_s=90.0,
            median_time_s=5.0,
            pages_per_second=0.5,
        )
        == "move_to_optional_candidate"
    )
    assert (
        default_set_signal(
            raw_successes=2,
            wins=1,
            total_time_s=300.0,
            median_time_s=45.0,
            pages_per_second=0.5,
        )
        == "keep_default_candidate"
    )
    assert (
        default_set_signal(
            raw_successes=2,
            wins=0,
            total_time_s=180.0,
            median_time_s=5.0,
            pages_per_second=5.0,
        )
        == "move_to_optional_candidate"
    )


def test_build_matrix_aggregates_reports_by_bucket_and_adapter(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    staging_root = tmp_path / "staging"
    source_a = sources_dir / "pdf/small/easy/a.pdf"
    source_b = sources_dir / "pdf/large/hard/b.pdf"
    _write_report(
        staging_root / "pdf/small/easy/a.pdf",
        _FakeReport(
            source_path=source_a,
            page_count=1,
            winner="inhouse",
            ranked={"inhouse": 0.0, "unstructured": 20.0},
            disqualified={},
            adapters={
                "inhouse": {"status": "ok", "timing_ms": 1000, "markdown_chars": 1000},
                "unstructured": {"status": "ok", "timing_ms": 2000, "markdown_chars": 900},
            },
        ),
    )
    _write_report(
        staging_root / "pdf/large/hard/b.pdf",
        _FakeReport(
            source_path=source_b,
            page_count=75,
            winner="unstructured",
            ranked={"unstructured": 15.0},
            disqualified={"inhouse": "Output too short"},
            adapters={
                "inhouse": {"status": "ok", "timing_ms": 3000, "markdown_chars": 10},
                "unstructured": {"status": "ok", "timing_ms": 4000, "markdown_chars": 5000},
            },
        ),
    )

    matrix = build_converter_benchmark_matrix(
        staging_root,
        sources_dir=sources_dir,
        measured_at="2026-04-23",
        hardware_label="test-host",
    )

    assert matrix["document_count"] == 2
    document_ids = {row["document_id"] for row in matrix["documents"]}
    assert "pdf/small/easy/a.pdf" in document_ids
    assert _row(matrix["bucket_adapter_summary"], bucket="1 page", adapter="inhouse")[
        "quality_tier"
    ] == "high"
    large_unstructured = _row(
        matrix["bucket_adapter_summary"],
        bucket="51-100 pages",
        adapter="unstructured",
    )
    assert large_unstructured["wins"] == 1
    assert large_unstructured["total_pages"] == 75
    assert large_unstructured["mean_time_s"] == 4.0
    assert large_unstructured["pages_per_second"] == 18.75
    assert _row(matrix["adapter_summary"], adapter="inhouse")["gate_pass_rate"] == 0.5


def test_build_matrix_reads_no_winner_report_at_document_root(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    staging_root = tmp_path / "staging"
    source = sources_dir / "pdf/mid/hard/no-winner.pdf"
    _write_report(
        staging_root / "pdf/mid/hard/no-winner.pdf",
        _FakeReport(
            source_path=source,
            page_count=20,
            winner=None,
            ranked={},
            disqualified={"inhouse": "index.md not found"},
            adapters={
                "inhouse": {"status": "error", "timing_ms": 500, "markdown_chars": 0},
            },
            promoted=False,
        ),
    )

    matrix = build_converter_benchmark_matrix(staging_root, sources_dir=sources_dir)

    row = _row(matrix["bucket_adapter_summary"], bucket="11-50 pages", adapter="inhouse")
    assert row["quality_tier"] == "failed"
    assert row["raw_successes"] == 0
    assert matrix["documents"][0]["winner"] == ""


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    staging_root = tmp_path / "staging"
    output_json = tmp_path / "matrix.json"
    output_md = tmp_path / "matrix.md"
    _write_report(
        staging_root / "pdf/small/easy/a.pdf",
        _FakeReport(
            source_path=sources_dir / "pdf/small/easy/a.pdf",
            page_count=1,
            winner="inhouse",
            ranked={"inhouse": 0.0},
            disqualified={},
            adapters={
                "inhouse": {"status": "ok", "timing_ms": 1000, "markdown_chars": 1000},
            },
        ),
    )

    rc = main(
        [
            str(staging_root),
            "--sources-dir",
            str(sources_dir),
            "--measured-at",
            "2026-04-23",
            "--hardware",
            "test-host",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert rc == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["document_count"] == 1
    assert "ADTM Converter Benchmark Matrix" in output_md.read_text(encoding="utf-8")


def test_render_markdown_matrix_includes_cost_note(tmp_path: Path) -> None:
    matrix = build_converter_benchmark_matrix(_empty_staging_root(tmp_path))

    markdown = render_markdown_matrix(matrix)

    assert "cloud_cost_usd" in markdown
    assert "$0" in markdown


@dataclass(frozen=True)
class _FakeReport:
    source_path: Path
    page_count: int
    winner: str | None
    ranked: dict[str, float]
    disqualified: dict[str, str]
    adapters: dict[str, dict[str, int | str]]
    promoted: bool = True


def _write_report(doc_root: Path, fake: _FakeReport) -> None:
    fake.source_path.parent.mkdir(parents=True, exist_ok=True)
    fake.source_path.write_text("source", encoding="utf-8")
    doc_root.mkdir(parents=True, exist_ok=True)
    for adapter, result in fake.adapters.items():
        adapter_dir = doc_root / adapter
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter_result.json").write_text(
            json.dumps(
                {
                    "method_name": adapter,
                    "status": result["status"],
                    "timing_ms": result["timing_ms"],
                    "markdown_chars": result["markdown_chars"],
                }
            ),
            encoding="utf-8",
        )
    report_dir = doc_root / "winner" if fake.promoted and fake.winner else doc_root
    report_dir.mkdir(parents=True, exist_ok=True)
    if fake.promoted and fake.winner:
        (report_dir / "adapter_result.json").write_text(
            json.dumps(
                {
                    "method_name": fake.winner,
                    "status": "ok",
                    "timing_ms": 999999,
                    "markdown_chars": 999999,
                }
            ),
            encoding="utf-8",
        )
    report = {
        "source_path": str(fake.source_path),
        "winner": fake.winner,
        "winner_staging_dir": str(report_dir) if fake.winner else None,
        "promoted": fake.promoted and fake.winner is not None,
        "traits": {
            "file_type": "pdf",
            "page_count": fake.page_count,
            "word_count": fake.page_count * 100,
        },
        "selection": {
            "winner": fake.winner,
            "winner_score": fake.ranked.get(fake.winner or "", 0.0),
            "ranked": [
                {"adapter_name": adapter, "total_score": score}
                for adapter, score in fake.ranked.items()
            ],
            "disqualified": fake.disqualified,
        },
        "adapter_timing_ms": {
            adapter: result["timing_ms"] for adapter, result in fake.adapters.items()
        },
    }
    (report_dir / "qa_report.json").write_text(json.dumps(report), encoding="utf-8")


def _row(rows: list[dict], **expected: str) -> dict:
    for row in rows:
        if all(row.get(key) == value for key, value in expected.items()):
            return row
    raise AssertionError(f"Missing row: {expected!r} in {rows!r}")


def _empty_staging_root(tmp_path: Path) -> Path:
    path = tmp_path / "empty"
    path.mkdir()
    return path
