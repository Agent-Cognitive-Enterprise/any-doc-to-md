from __future__ import annotations

import json
from pathlib import Path

from anydoc2md.cli import main
from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIRED_MD,
    PARAGRAPH_REPAIR_REPORT_JSON,
)


def test_cli_paragraph_repair_preserves_raw_and_publishes_fixed(
    tmp_path: Path,
) -> None:
    source = _row_sliced_fixture_path()
    output_dir = tmp_path / "auto"

    rc = main(["convert", str(source), "--output-dir", str(output_dir)])

    assert rc == 0
    published = (output_dir / "index.md").read_text(encoding="utf-8")
    # This e2e test intentionally inspects tournament staging: raw adapter
    # preservation and winner promotion are part of the behavior under test.
    raw_adapter = (
        output_dir / ".any-doc-to-md" / "staging" / "inhouse" / "index.md"
    ).read_text(encoding="utf-8")
    winner_dir = output_dir / ".any-doc-to-md" / "staging" / "winner"
    fixed = (winner_dir / "index_fixed.md").read_text(encoding="utf-8")
    result = json.loads((output_dir / "anydoc2md-result.json").read_text(encoding="utf-8"))

    assert _joined_fragment() in published
    assert _row_slice_boundary() not in published
    assert _row_slice_boundary() in raw_adapter
    assert _joined_fragment() not in raw_adapter
    assert fixed == published
    assert (winner_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert (winner_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
    assert result["winner"] == "inhouse"
    assert result["selection"]["ranked"][0]["check_scores"]["paragraph_not_row_sliced"] == 0.0


def test_cli_paragraph_repair_off_publishes_raw_and_reports_warning(
    tmp_path: Path,
) -> None:
    source = _row_sliced_fixture_path()
    output_dir = tmp_path / "off"

    rc = main([
        "convert",
        str(source),
        "--output-dir",
        str(output_dir),
        "--paragraph-repair",
        "off",
    ])

    assert rc == 0
    published = (output_dir / "index.md").read_text(encoding="utf-8")
    winner_dir = output_dir / ".any-doc-to-md" / "staging" / "winner"
    result = json.loads((output_dir / "anydoc2md-result.json").read_text(encoding="utf-8"))

    assert _row_slice_boundary() in published
    assert _joined_fragment() not in published
    assert not (winner_dir / "index_fixed.md").exists()
    assert not (winner_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (winner_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
    assert result["winner"] == "inhouse"
    assert result["selection"]["ranked"][0]["check_scores"]["paragraph_not_row_sliced"] > 0.0


def _row_sliced_fixture_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "benchmark-corpus"
        / "row-sliced-note.txt"
    )


def _joined_fragment() -> str:
    return (
        "The inspection team arrived at the north intake after the first alarm "
        "and found that the overflow"
    )


def _row_slice_boundary() -> str:
    # Coupled to row-sliced-note.txt by design: the fixture must preserve this
    # blank-line split so the test can distinguish raw vs. repaired output.
    return "\n\nafter the first alarm and found that the overflow\n"
