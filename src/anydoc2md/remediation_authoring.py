"""Deterministic project-local remediation scaffold authoring."""

from __future__ import annotations

import json
from pathlib import Path


def author_project_local_scaffolds(
    *,
    report_data: dict,
    anydoc2md_dir: Path,
    doc_key: str,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Write deterministic project-local hook scaffolds from persisted findings."""
    remediation_plan = report_data.get("remediation_plan") or {}
    tasks = remediation_plan.get("tasks") or []
    if not tasks:
        return {}

    written: dict[str, Path] = {}
    qa_path = anydoc2md_dir / "qa-extensions" / f"{doc_key}.py"
    inhouse_path = anydoc2md_dir / "inhouse-extensions" / f"{doc_key}.py"

    if overwrite or not qa_path.exists():
        _write_text(qa_path, _render_qa_extension(doc_key, tasks))
        written["qa_extension"] = qa_path
    if overwrite or not inhouse_path.exists():
        _write_text(inhouse_path, _render_inhouse_extension(doc_key, tasks, remediation_plan))
        written["inhouse_extension"] = inhouse_path
    return written


def _render_qa_extension(doc_key: str, tasks: list[dict]) -> str:
    tasks_literal = json.dumps(tasks, indent=2, ensure_ascii=True)
    return (
        f'"""Generated QA remediation scaffold for {doc_key}.\n'
        "Review and replace the no-op hook functions with deterministic checks.\n"
        '"""\n\n'
        "from anydoc2md.output_qa.checks import CheckResult\n\n"
        f"REMEDIATION_TASKS = {tasks_literal}\n\n"
        "def get_disabled_checks():\n"
        "    return []\n\n"
        "def get_additional_md_only_checks():\n"
        "    return []\n\n"
        "def get_additional_md_with_dir_checks():\n"
        "    return []\n\n"
        "def get_additional_source_checks():\n"
        "    return []\n\n"
        "def describe_generated_tasks():\n"
        "    return REMEDIATION_TASKS\n"
    )


def _render_inhouse_extension(doc_key: str, tasks: list[dict], remediation_plan: dict) -> str:
    tasks_literal = json.dumps(tasks, indent=2, ensure_ascii=True)
    target_adapter = remediation_plan.get("target_adapter", "inhouse")
    return (
        f'"""Generated in-house remediation scaffold for {doc_key}.\n'
        "Review and replace the no-op hook with deterministic staging edits.\n"
        '"""\n\n'
        f"TARGET_ADAPTER = {target_adapter!r}\n"
        f"REMEDIATION_TASKS = {tasks_literal}\n\n"
        "def apply_inhouse_extension(source_path, staging_dir, converter_name):\n"
        "    return None\n"
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
