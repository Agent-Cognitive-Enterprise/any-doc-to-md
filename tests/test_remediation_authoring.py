from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from anydoc2md.remediation_authoring import author_project_local_scaffolds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _report(violation_type: str, severity: str = "major", **extra) -> dict:
    task = {
        "violation_type": violation_type,
        "severity": severity,
        "evidence": f"Evidence for {violation_type}.",
        "root_cause": f"Root cause of {violation_type}.",
        "target_adapter": "inhouse",
        "suggested_fix_area": "pdf_converter",
        "suggested_fix": f"Fix {violation_type}.",
        **extra,
    }
    return {"remediation_plan": {"target_adapter": "inhouse", "tasks": [task]}}


# ---------------------------------------------------------------------------
# Existing contract tests
# ---------------------------------------------------------------------------

def test_writes_expected_files(tmp_path: Path) -> None:
    written = author_project_local_scaffolds(
        report_data=_report("reading_order"),
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )
    qa_path = tmp_path / "qa-extensions" / "org__doc.txt.py"
    fix_path = tmp_path / "fix-extensions" / "org__doc.txt.py"
    assert written["qa_extension"] == qa_path
    assert written["fix_extension"] == fix_path
    assert "REMEDIATION_TASKS" in qa_path.read_text(encoding="utf-8")
    assert "apply_fix_extension" in fix_path.read_text(encoding="utf-8")
    assert "reading_order" in qa_path.read_text(encoding="utf-8")


def test_does_not_overwrite_by_default(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa-extensions" / "org__doc.txt.py"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text("# custom\n", encoding="utf-8")
    written = author_project_local_scaffolds(
        report_data=_report("reading_order"),
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )
    assert "qa_extension" not in written  # per overwrite=False default
    assert qa_path.read_text(encoding="utf-8") == "# custom\n"


def test_skips_empty_plans(tmp_path: Path) -> None:
    written = author_project_local_scaffolds(
        report_data={"remediation_plan": {"tasks": []}},
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )
    assert written == {}


# ---------------------------------------------------------------------------
# QA extension — known violation type wires existing check
# ---------------------------------------------------------------------------

def test_known_type_imports_existing_check(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("caption_detachment"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    src = (tmp_path / "qa-extensions" / "doc.py").read_text(encoding="utf-8")
    assert "check_caption_near_image" in src
    assert "get_additional_md_only_checks" in src


def test_known_type_qa_extension_is_importable_and_returns_check(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("caption_detachment"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    qa_path = tmp_path / "qa-extensions" / "doc.py"
    spec = importlib.util.spec_from_file_location("_qa_ext_test", qa_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.get_additional_md_only_checks()
    assert len(checks) == 1
    from anydoc2md.output_qa.checks import check_caption_near_image
    assert checks[0] is check_caption_near_image


def test_known_type_deduplicates_same_check(tmp_path: Path) -> None:
    report = {
        "remediation_plan": {
            "target_adapter": "inhouse",
            "tasks": [
                {"violation_type": "caption_detachment", "severity": "major",
                 "evidence": "e1", "root_cause": "", "suggested_fix": ""},
                {"violation_type": "caption_detachment", "severity": "major",
                 "evidence": "e2", "root_cause": "", "suggested_fix": ""},
            ],
        }
    }
    author_project_local_scaffolds(report_data=report, anydoc2md_dir=tmp_path, doc_key="doc")
    src = (tmp_path / "qa-extensions" / "doc.py").read_text(encoding="utf-8")
    assert src.count("check_caption_near_image") == 2  # import + list entry, not 3+


# ---------------------------------------------------------------------------
# QA extension — unknown violation type generates named stub with evidence
# ---------------------------------------------------------------------------

def test_unknown_type_generates_named_stub(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("reading_order"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    src = (tmp_path / "qa-extensions" / "doc.py").read_text(encoding="utf-8")
    assert "def _check_reading_order" in src
    assert "Evidence for reading_order" in src
    assert "TODO" in src


def test_unknown_type_stub_is_importable_and_returns_pass(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("reading_order"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    qa_path = tmp_path / "qa-extensions" / "doc.py"
    spec = importlib.util.spec_from_file_location("_qa_stub_test", qa_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.get_additional_md_only_checks()
    assert len(checks) == 1
    result = checks[0]("some markdown text")
    assert result.status == "pass"
    assert result.name == "reading_order"


# ---------------------------------------------------------------------------
# QA extension — mixed known and unknown types
# ---------------------------------------------------------------------------

def test_mixed_types_wire_known_and_stub_unknown(tmp_path: Path) -> None:
    report = {
        "remediation_plan": {
            "target_adapter": "inhouse",
            "tasks": [
                {"violation_type": "caption_detachment", "severity": "major",
                 "evidence": "caption far", "root_cause": "", "suggested_fix": ""},
                {"violation_type": "reading_order", "severity": "major",
                 "evidence": "wrong order", "root_cause": "", "suggested_fix": ""},
            ],
        }
    }
    author_project_local_scaffolds(report_data=report, anydoc2md_dir=tmp_path, doc_key="doc")
    src = (tmp_path / "qa-extensions" / "doc.py").read_text(encoding="utf-8")
    assert "check_caption_near_image" in src
    assert "def _check_reading_order" in src

    qa_path = tmp_path / "qa-extensions" / "doc.py"
    spec = importlib.util.spec_from_file_location("_qa_mixed_test", qa_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.get_additional_md_only_checks()
    assert len(checks) == 2


# ---------------------------------------------------------------------------
# Inhouse extension — known fixable type generates working code
# ---------------------------------------------------------------------------

def test_double_bullets_generates_working_fix(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("double_bullets"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    src = (tmp_path / "fix-extensions" / "doc.py").read_text(encoding="utf-8")
    assert "re.sub" in src
    assert "index.md" in src
    assert "pass" not in src


def test_double_bullets_fix_actually_fixes_content(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("double_bullets"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    # Write a staging dir with a broken index.md
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.md").write_text("- \u2022 item one\n- \u2022 item two\n", encoding="utf-8")

    ext_path = tmp_path / "fix-extensions" / "doc.py"
    spec = importlib.util.spec_from_file_location("_inhouse_ext_test", ext_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply_fix_extension(None, staging, "inhouse")

    result = (staging / "index.md").read_text(encoding="utf-8")
    assert "\u2022" not in result
    assert "- item one" in result
    assert "- item two" in result


# ---------------------------------------------------------------------------
# Inhouse extension — unknown type generates evidence-rich stub
# ---------------------------------------------------------------------------

def test_unknown_type_inhouse_stub_embeds_evidence(tmp_path: Path) -> None:
    author_project_local_scaffolds(
        report_data=_report("reading_order"),
        anydoc2md_dir=tmp_path,
        doc_key="doc",
    )
    src = (tmp_path / "fix-extensions" / "doc.py").read_text(encoding="utf-8")
    assert "reading_order" in src
    assert "Evidence for reading_order" in src
    assert "TODO" in src
