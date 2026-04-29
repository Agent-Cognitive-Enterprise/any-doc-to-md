from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from anydoc2md.cli import main
from anydoc2md.scaffold_staging import stage_project_scaffolds


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
    fix_src = anydoc2md_dir / "fix-extensions" / "doc.txt.py"
    qa_src.parent.mkdir(parents=True)
    fix_src.parent.mkdir(parents=True)
    qa_src.write_text("# qa", encoding="utf-8")
    fix_src.write_text("# fix", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir)

    assert (staging_dir / "qa_extension.py").read_text(encoding="utf-8") == "# qa"
    assert (staging_dir / "fix_extension.py").read_text(encoding="utf-8") == "# fix"


def test_stage_project_scaffolds_noop_when_no_scaffolds(tmp_path: Path) -> None:
    stage_project_scaffolds(tmp_path / ".any-doc-to-md", tmp_path / "doc.txt", tmp_path / "staging")
    assert not (tmp_path / "staging").exists()


def test_stage_project_qa_only_copies_as_qa_extension(tmp_path: Path) -> None:
    project_qa = tmp_path / "project_qa.py"
    project_qa.write_text("# project qa", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(tmp_path / ".any-doc-to-md", tmp_path / "doc.txt", staging_dir, qa=project_qa)

    assert (staging_dir / "qa_extension.py").read_text(encoding="utf-8") == "# project qa"
    assert not (staging_dir / "_project_qa_extension.py").exists()


def test_stage_project_qa_merges_when_doc_scaffold_also_exists(tmp_path: Path) -> None:
    project_qa = tmp_path / "project_qa.py"
    project_qa.write_text("# project qa", encoding="utf-8")
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    doc_qa = anydoc2md_dir / "qa-extensions" / "doc.txt.py"
    doc_qa.parent.mkdir(parents=True)
    doc_qa.write_text("# doc qa", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir, qa=project_qa)

    assert (staging_dir / "_project_qa_extension.py").read_text(encoding="utf-8") == "# project qa"
    assert (staging_dir / "_doc_qa_extension.py").read_text(encoding="utf-8") == "# doc qa"
    merged = (staging_dir / "qa_extension.py").read_text(encoding="utf-8")
    assert "_project_qa_extension.py" in merged
    assert "_doc_qa_extension.py" in merged
    assert "get_additional_md_only_checks" in merged


def test_stage_project_fix_merges_when_doc_scaffold_also_exists(tmp_path: Path) -> None:
    project_fix = tmp_path / "project_fix.py"
    project_fix.write_text("# project fix", encoding="utf-8")
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    doc_fix = anydoc2md_dir / "fix-extensions" / "doc.txt.py"
    doc_fix.parent.mkdir(parents=True)
    doc_fix.write_text("# doc fix", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir, fix=project_fix)

    assert (staging_dir / "_project_fix_extension.py").read_text(encoding="utf-8") == "# project fix"
    assert (staging_dir / "_doc_fix_extension.py").read_text(encoding="utf-8") == "# doc fix"
    merged = (staging_dir / "fix_extension.py").read_text(encoding="utf-8")
    assert "_project_fix_extension.py" in merged
    assert "_doc_fix_extension.py" in merged
    assert "apply_fix_extension" in merged


def test_stage_project_qa_all_merges_all_extensions(tmp_path: Path) -> None:
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    qa_dir = anydoc2md_dir / "qa-extensions"
    qa_dir.mkdir(parents=True)
    (qa_dir / "doc-a.pdf.py").write_text("# qa-a", encoding="utf-8")
    (qa_dir / "doc-b.html.py").write_text("# qa-b", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir, qa_all=True)

    assert (staging_dir / "_all_qa_0.py").exists()
    assert (staging_dir / "_all_qa_1.py").exists()
    merged = (staging_dir / "qa_extension.py").read_text(encoding="utf-8")
    assert "_all_qa_0.py" in merged
    assert "_all_qa_1.py" in merged
    assert "get_additional_md_only_checks" in merged


def test_stage_project_fix_all_merges_all_extensions(tmp_path: Path) -> None:
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    fix_dir = anydoc2md_dir / "fix-extensions"
    fix_dir.mkdir(parents=True)
    (fix_dir / "doc-a.pdf.py").write_text("# fix-a", encoding="utf-8")
    (fix_dir / "doc-b.html.py").write_text("# fix-b", encoding="utf-8")
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir, fix_all=True)

    assert (staging_dir / "_all_fix_0.py").exists()
    assert (staging_dir / "_all_fix_1.py").exists()
    merged = (staging_dir / "fix_extension.py").read_text(encoding="utf-8")
    assert "_all_fix_0.py" in merged
    assert "apply_fix_extension" in merged


def test_stage_project_qa_all_noop_when_dir_empty(tmp_path: Path) -> None:
    anydoc2md_dir = tmp_path / ".any-doc-to-md"
    (anydoc2md_dir / "qa-extensions").mkdir(parents=True)
    staging_dir = tmp_path / "staging"

    stage_project_scaffolds(anydoc2md_dir, tmp_path / "doc.txt", staging_dir, qa_all=True)

    assert not staging_dir.exists()


def test_convert_rejects_missing_qa(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")

    rc = main(["convert", str(source), "--output-dir", str(tmp_path / "out"),
               "--qa", str(tmp_path / "nonexistent.py")])

    assert rc == 2
    assert "--qa" in capsys.readouterr().err


def test_convert_rejects_missing_fix(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")

    rc = main(["convert", str(source), "--output-dir", str(tmp_path / "out"),
               "--fix", str(tmp_path / "nonexistent.py")])

    assert rc == 2
    assert "--fix" in capsys.readouterr().err


def test_convert_rejects_qa_and_qa_all_together(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")
    qa_file = tmp_path / "qa.py"
    qa_file.write_text("# qa", encoding="utf-8")

    rc = main(["convert", str(source), "--output-dir", str(tmp_path / "out"),
               "--qa", str(qa_file), "--qa-all"])

    assert rc == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_convert_rejects_fix_and_fix_all_together(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x", encoding="utf-8")
    fix_file = tmp_path / "fix.py"
    fix_file.write_text("# fix", encoding="utf-8")

    rc = main(["convert", str(source), "--output-dir", str(tmp_path / "out"),
               "--fix", str(fix_file), "--fix-all"])

    assert rc == 2
    assert "mutually exclusive" in capsys.readouterr().err
