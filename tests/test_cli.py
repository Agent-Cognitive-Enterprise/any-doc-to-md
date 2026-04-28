from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from anydoc2md.cli import main, _stage_project_scaffolds


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
        judge_verdict=None,
        remediation_plan=None,
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
        judge_verdict=None,
        remediation_plan=None,
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
        judge_verdict=None,
        remediation_plan=None,
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


def test_convert_project_dir_routes_anydoc2md_dir(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    output_dir = tmp_path / "out"
    project_dir = tmp_path / "project"
    winner_dir = tmp_path / "winner"
    source.write_text("source", encoding="utf-8")
    winner_dir.mkdir()
    (winner_dir / "index.md").write_text("# ok", encoding="utf-8")

    result = SimpleNamespace(
        winner="inhouse",
        winner_staging_dir=winner_dir,
        judge_verdict=None,
        remediation_plan=None,
        to_dict=lambda: {"winner": "inhouse"},
    )

    with patch("anydoc2md.cli.run_full_tournament", return_value=result):
        rc = main([
            "convert", str(source),
            "--output-dir", str(output_dir),
            "--project-dir", str(project_dir),
        ])

    assert rc == 0
    assert (output_dir / "anydoc2md-result.json").exists()
    assert not (output_dir / ".any-doc-to-md").exists()


def test_stage_project_scaffolds_copies_existing_files(tmp_path: Path) -> None:
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    qa_src = anydoc2md_dir / "qa-extensions" / "doc.txt.py"
    inhouse_src = anydoc2md_dir / "inhouse-extensions" / "doc.txt.py"
    qa_src.parent.mkdir(parents=True)
    inhouse_src.parent.mkdir(parents=True)
    qa_src.write_text("# qa", encoding="utf-8")
    inhouse_src.write_text("# inhouse", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    source = tmp_path / "doc.txt"
    _stage_project_scaffolds(anydoc2md_dir, source, staging_dir)

    assert (staging_dir / "qa_extension.py").read_text(encoding="utf-8") == "# qa"
    assert (staging_dir / "inhouse_extension.py").read_text(encoding="utf-8") == "# inhouse"


def test_stage_project_scaffolds_noop_when_no_scaffolds(tmp_path: Path) -> None:
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    staging_dir = tmp_path / "staging"
    source = tmp_path / "doc.txt"

    _stage_project_scaffolds(anydoc2md_dir, source, staging_dir)

    assert not staging_dir.exists()
