from __future__ import annotations

import json
from pathlib import Path

from anydoc2md.converter_benchmark_matrix import build_converter_benchmark_matrix
from anydoc2md.format_converters.tournament.orchestrator import run_full_tournament
from anydoc2md.settings import AUDIT_MODE_LIGHT


def test_public_benchmark_corpus_runs_default_light_benchmark(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sources = [
        repo_root / "examples/benchmark-corpus/field-note.txt",
        repo_root / "examples/benchmark-corpus/ops-brief.txt",
        repo_root / "src/anydoc2md/probe_assets/probe_source_reference.pdf",
    ]
    staging_root = tmp_path / "public-benchmark"

    for source in sources:
        result = run_full_tournament(
            source,
            staging_root / source.stem,
            audit_mode=AUDIT_MODE_LIGHT,
            timeout_s=120,
        )
        assert result.winner == "inhouse"
        assert result.winner_staging_dir is not None
        qa_report = result.winner_staging_dir / "qa_report.json"
        qa_report.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    matrix = build_converter_benchmark_matrix(staging_root, sources_dir=repo_root)

    assert matrix["document_count"] == 3
    document_ids = {row["document_id"] for row in matrix["documents"]}
    assert "examples/benchmark-corpus/field-note.txt" in document_ids
    assert "examples/benchmark-corpus/ops-brief.txt" in document_ids
    assert "src/anydoc2md/probe_assets/probe_source_reference.pdf" in document_ids
