from __future__ import annotations

from pathlib import Path

from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIRED_MD,
    PARAGRAPH_REPAIR_REPORT_JSON,
    apply_paragraph_continuity_repair,
)


def test_missing_index_md_clears_owned_output_directories(
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "staging" / "inhouse"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / PARAGRAPH_REPAIRED_MD).mkdir()
    (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).mkdir()
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.attempted is False
    assert report.accepted is False
    assert report.reason == "index_md_missing"
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
