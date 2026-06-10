from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from anydoc2md.cli import _print_adapter_table, main
from anydoc2md.output_qa.scoring import ScoreCard
from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIRED_MD,
    PARAGRAPH_REPAIR_REPORT_JSON,
)
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
    assert run_mock.call_args.kwargs["paragraph_repair"] == "auto"
    assert "winner=inhouse" in capsys.readouterr().out


def test_convert_paragraph_repair_off_is_forwarded(tmp_path: Path) -> None:
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
        rc = main([
            "convert",
            str(source),
            "--output-dir",
            str(output_dir),
            "--paragraph-repair",
            "off",
        ])

    assert rc == 0
    assert run_mock.call_args.kwargs["paragraph_repair"] == "off"


def test_convert_default_paragraph_repair_changes_real_inhouse_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "row-sliced-note.txt"
    source.write_text(_short_row_sliced_source(), encoding="utf-8")
    auto_output = tmp_path / "auto"
    off_output = tmp_path / "off"

    auto_rc = main(["convert", str(source), "--output-dir", str(auto_output)])
    off_rc = main([
        "convert",
        str(source),
        "--output-dir",
        str(off_output),
        "--paragraph-repair",
        "off",
    ])

    assert auto_rc == 0
    assert off_rc == 0
    auto_md = (auto_output / "index.md").read_text(encoding="utf-8")
    off_md = (off_output / "index.md").read_text(encoding="utf-8")
    joined = (
        "The inspection team arrived at the north intake after the first alarm "
        "and found that the overflow"
    )
    assert joined in auto_md
    assert joined not in off_md
    assert "\n\nafter the first alarm and found that the overflow\n" in off_md
    assert "\n\nafter the first alarm and found that the overflow\n" not in auto_md

    winner_dir = auto_output / ".any-doc-to-md" / "staging" / "winner"
    assert (winner_dir / "index_fixed.md").exists()
    assert (winner_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert (winner_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


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


def test_convert_rejects_invalid_paragraph_repair_mode(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main([
            "convert",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--paragraph-repair",
            "always",
        ])

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


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


def _short_row_sliced_source() -> str:
    return "\n\n".join(
        [
            "The inspection team arrived at the north intake",
            "after the first alarm and found that the overflow",
            "channel was carrying shallow water across the grated",
            "walkway while the upstream valve remained partially",
            "open and the temporary pump continued cycling",
            "every few minutes without recording a stable",
            "pressure reading.",
            "The operator reported that the same pattern",
            "had appeared during the previous storm and that",
            "the manual log showed brief pressure drops",
            "near the east manifold whenever the backup",
            "generator switched load while the",
            "backup pump continued running.",
        ]
    ) + "\n"


# ---------------------------------------------------------------------------
# Adapter timing table
# ---------------------------------------------------------------------------

def _make_adapter_result(name: str, timing_ms: int, status: str = "ok"):
    return SimpleNamespace(method_name=name, timing_ms=timing_ms, status=status)


def _make_selection(ranked, disqualified=None):
    return SimpleNamespace(ranked=ranked, disqualified=disqualified or {})


def test_print_adapter_table_shows_timing_and_score(capsys) -> None:
    result = SimpleNamespace(
        winner="inhouse",
        adapter_results=[
            _make_adapter_result("inhouse", 12),
            _make_adapter_result("docling", 1823),
        ],
        selection=_make_selection(
            ranked=[
                ScoreCard("inhouse", 0.0, {}, 0, 0, 5),
                ScoreCard("docling", 15.0, {}, 1, 0, 4),
            ]
        ),
    )

    _print_adapter_table(result)

    out = capsys.readouterr().out
    assert "inhouse" in out
    assert "docling" in out
    assert "12ms" in out
    assert "1823ms" in out
    assert "0.0" in out
    assert "15.0" in out
    assert "[winner]" in out


def test_print_adapter_table_shows_timeout_status(capsys) -> None:
    result = SimpleNamespace(
        winner="inhouse",
        adapter_results=[
            _make_adapter_result("inhouse", 12),
            _make_adapter_result("docling", 615000, status="timeout"),
        ],
        selection=_make_selection(
            ranked=[ScoreCard("inhouse", 0.0, {}, 0, 0, 5)],
            disqualified={},
        ),
    )

    _print_adapter_table(result)

    out = capsys.readouterr().out
    assert "timeout" in out
    assert "[winner]" in out


def test_print_adapter_table_shows_disqualified(capsys) -> None:
    result = SimpleNamespace(
        winner="inhouse",
        adapter_results=[
            _make_adapter_result("inhouse", 12),
            _make_adapter_result("pandoc", 50),
        ],
        selection=_make_selection(
            ranked=[ScoreCard("inhouse", 0.0, {}, 0, 0, 5)],
            disqualified={"pandoc": "index.md missing"},
        ),
    )

    _print_adapter_table(result)

    out = capsys.readouterr().out
    assert "disq" in out


def test_print_adapter_table_noop_without_adapter_results(capsys) -> None:
    result = SimpleNamespace(winner="inhouse")
    _print_adapter_table(result)
    assert capsys.readouterr().out == ""
