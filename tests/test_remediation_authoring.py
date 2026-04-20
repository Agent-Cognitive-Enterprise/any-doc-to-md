from __future__ import annotations

import json
from pathlib import Path

from anydoc2md.remediation_authoring import author_project_local_scaffolds


def _report_data() -> dict:
    return {
        "remediation_plan": {
            "target_adapter": "inhouse",
            "tasks": [
                {
                    "violation_type": "reading_order",
                    "severity": "major",
                    "evidence": "Paragraph continuation appears after the figure block.",
                    "pages": [2],
                    "target_adapter": "inhouse",
                    "compare_against": "docling",
                    "suggested_test": "Add a regression fixture.",
                    "suggested_fix_area": "pdf_converter block ordering",
                    "suggested_fix": "Adjust ordering.",
                }
            ],
        }
    }


def test_author_project_local_scaffolds_writes_expected_files(tmp_path: Path) -> None:
    written = author_project_local_scaffolds(
        report_data=_report_data(),
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )

    qa_path = tmp_path / "qa-extensions" / "org__doc.txt.py"
    inhouse_path = tmp_path / "inhouse-extensions" / "org__doc.txt.py"
    assert written["qa_extension"] == qa_path
    assert written["inhouse_extension"] == inhouse_path
    assert "REMEDIATION_TASKS" in qa_path.read_text(encoding="utf-8")
    assert "apply_inhouse_extension" in inhouse_path.read_text(encoding="utf-8")
    assert "reading_order" in qa_path.read_text(encoding="utf-8")


def test_author_project_local_scaffolds_does_not_overwrite_by_default(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa-extensions" / "org__doc.txt.py"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text("# custom\n", encoding="utf-8")

    written = author_project_local_scaffolds(
        report_data=_report_data(),
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )

    assert "qa_extension" not in written
    assert qa_path.read_text(encoding="utf-8") == "# custom\n"


def test_author_project_local_scaffolds_skips_empty_plans(tmp_path: Path) -> None:
    written = author_project_local_scaffolds(
        report_data={"remediation_plan": {"tasks": []}},
        anydoc2md_dir=tmp_path,
        doc_key="org__doc.txt",
    )
    assert written == {}
