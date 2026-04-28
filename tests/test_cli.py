from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from anydoc2md.cli import main


def test_adapters_command_lists_default_and_available(capsys) -> None:
    rc = main(["adapters"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Default adapters: inhouse" in out
    assert "Available adapters:" in out
    assert "markitdown" in out


def test_convert_publishes_winner_to_output_dir(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    winner_dir = tmp_path / "winner"
    source.write_text("source", encoding="utf-8")
    winner_dir.mkdir()
    (winner_dir / "index.md").write_text("# Converted", encoding="utf-8")

    result = SimpleNamespace(
        winner="inhouse",
        winner_staging_dir=winner_dir,
        to_dict=lambda: {"winner": "inhouse"},
    )

    with patch("anydoc2md.cli.run_full_tournament", return_value=result) as run_mock:
        rc = main(["convert", str(source), "--output-dir", str(output_dir)])

    assert rc == 0
    assert (output_dir / "index.md").read_text(encoding="utf-8") == "# Converted"
    assert (output_dir / "anydoc2md-result.json").exists()
    run_mock.assert_called_once()
    assert run_mock.call_args.kwargs["adapters"] is None
    assert run_mock.call_args.kwargs["audit_mode"] == "light"
    assert "winner=inhouse" in capsys.readouterr().out


def test_convert_all_adapters_passes_explicit_adapter_list(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    winner_dir = tmp_path / "winner"
    source.write_text("source", encoding="utf-8")
    winner_dir.mkdir()
    (winner_dir / "index.md").write_text("# Converted", encoding="utf-8")
    result = SimpleNamespace(
        winner="inhouse",
        winner_staging_dir=winner_dir,
        to_dict=lambda: {"winner": "inhouse"},
    )

    with patch("anydoc2md.cli.run_full_tournament", return_value=result) as run_mock:
        rc = main(["convert", str(source), "-o", str(output_dir), "--all-adapters"])

    assert rc == 0
    assert run_mock.call_args.kwargs["adapters"] == [
        "inhouse",
        "markitdown",
        "docling",
        "unstructured",
        "pandoc",
        "marker",
    ]


def test_convert_returns_error_when_no_winner(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    source.write_text("source", encoding="utf-8")
    result = SimpleNamespace(
        winner=None,
        winner_staging_dir=None,
        to_dict=lambda: {"winner": None},
    )

    with patch("anydoc2md.cli.run_full_tournament", return_value=result):
        rc = main(["convert", str(source), "-o", str(output_dir)])

    assert rc == 1
    assert "no winning conversion" in capsys.readouterr().err
    assert (output_dir / "anydoc2md-result.json").exists()


def test_convert_rejects_missing_source(tmp_path: Path, capsys) -> None:
    rc = main(["convert", str(tmp_path / "missing.txt"), "-o", str(tmp_path / "out")])

    assert rc == 2
    assert "source file not found" in capsys.readouterr().err
