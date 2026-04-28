"""Deterministic project-local remediation scaffold authoring."""

from __future__ import annotations

import json
import re
from pathlib import Path

# Maps LLM judge violation_type values to existing layer-1 check functions.
# Matched types are wired automatically; unmatched types get named stubs.
_VIOLATION_TO_LAYER1_CHECK: dict[str, str] = {
    "caption_detachment": "check_caption_near_image",
    "fragmented_heading": "check_heading_not_fragmented",
    "double_bullets": "check_no_double_bullets",
    "list_sequence": "check_numbered_list_sequential",
    "numbered_list_restart": "check_numbered_list_sequential",
    "box_title_detachment": "check_box_title_precedes_content",
    "image_size": "check_image_size_plausible",
    "repeated_headings": "check_no_repeated_headings",
}

# Maps violation_type values to working inhouse-extension fix bodies (4-space indent).
_VIOLATION_TO_FIX_BODY: dict[str, str] = {
    "double_bullets": (
        "    import re\n"
        "    from pathlib import Path as _Path\n"
        "    index_path = _Path(staging_dir) / \"index.md\"\n"
        "    text = index_path.read_text(encoding=\"utf-8\")\n"
        "    fixed = re.sub(r'^([-*])\\s+[\\u2022\\-\\*]\\s+', r'\\1 ', text, flags=re.MULTILINE)\n"
        "    if fixed != text:\n"
        "        index_path.write_text(fixed, encoding=\"utf-8\")\n"
    ),
}


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


def _stub_fn_name(violation_type: str) -> str:
    return "_check_" + re.sub(r"[^a-z0-9]+", "_", violation_type.lower()).strip("_")


def _render_qa_extension(doc_key: str, tasks: list[dict]) -> str:
    tasks_literal = json.dumps(tasks, indent=2, ensure_ascii=True)

    known_checks: list[str] = []
    seen_checks: set[str] = set()
    stub_tasks: list[dict] = []

    for task in tasks:
        vtype = task.get("violation_type", "")
        check_fn = _VIOLATION_TO_LAYER1_CHECK.get(vtype)
        if check_fn and check_fn not in seen_checks:
            known_checks.append(check_fn)
            seen_checks.add(check_fn)
        elif not check_fn:
            stub_tasks.append(task)

    import_names = ["CheckResult"] + known_checks
    imports = "from anydoc2md.output_qa.checks import " + ", ".join(import_names) + "\n"

    stub_fn_blocks: list[str] = []
    for task in stub_tasks:
        vtype = task.get("violation_type", "unknown")
        fn = _stub_fn_name(vtype)
        severity = task.get("severity", "")
        evidence = task.get("evidence", "")
        root_cause = task.get("root_cause", "")
        comment_lines = [f"    # violation_type: {vtype} (severity: {severity})"]
        if evidence:
            comment_lines.append(f"    # evidence: {evidence}")
        if root_cause:
            comment_lines.append(f"    # root_cause: {root_cause}")
        comment_lines.append("    # TODO: implement deterministic check for this issue class.")
        body = "\n".join(comment_lines)
        stub_fn_blocks.append(
            f"def {fn}(md_text: str):\n"
            f"{body}\n"
            f"    return CheckResult(\n"
            f'        name="{vtype}", layer=1, status="pass",\n'
            f'        message="Stub check — implement to detect this issue.",\n'
            f"    )\n"
        )

    all_fn_names = known_checks + [_stub_fn_name(t.get("violation_type", "unknown")) for t in stub_tasks]
    checks_list = "[" + ", ".join(all_fn_names) + "]" if all_fn_names else "[]"

    has_known = bool(known_checks)
    docstring_note = (
        "Known violation types are wired to existing checks automatically.\n"
        "Stub checks mark unknown types — implement TODO bodies before relying on them.\n"
        if has_known else
        "Review and replace stub functions with deterministic checks.\n"
    )

    stub_section = ("\n\n" + "\n\n".join(stub_fn_blocks)) if stub_fn_blocks else ""

    return (
        f'"""Generated QA remediation scaffold for {doc_key}.\n{docstring_note}"""\n\n'
        f"{imports}\n"
        f"REMEDIATION_TASKS = {tasks_literal}\n"
        f"\n\ndef get_disabled_checks():\n    return []\n"
        f"\n\ndef get_additional_md_only_checks():\n    return {checks_list}\n"
        f"\n\ndef get_additional_md_with_dir_checks():\n    return []\n"
        f"\n\ndef get_additional_source_checks():\n    return []\n"
        f"\n\ndef describe_generated_tasks():\n    return REMEDIATION_TASKS\n"
        f"{stub_section}"
    )


def _render_inhouse_extension(doc_key: str, tasks: list[dict], remediation_plan: dict) -> str:
    tasks_literal = json.dumps(tasks, indent=2, ensure_ascii=True)
    target_adapter = remediation_plan.get("target_adapter", "inhouse")

    fix_parts: list[str] = []
    seen_vtypes: set[str] = set()

    for task in tasks:
        vtype = task.get("violation_type", "")
        if vtype in seen_vtypes:
            continue
        seen_vtypes.add(vtype)
        fix_body = _VIOLATION_TO_FIX_BODY.get(vtype)
        if fix_body:
            fix_parts.append(f"    # fix: {vtype}\n" + fix_body)
        else:
            evidence = task.get("evidence", "")
            root_cause = task.get("root_cause", "")
            suggested_fix = task.get("suggested_fix", "")
            fix_area = task.get("suggested_fix_area", "")
            lines = [f"    # violation_type: {vtype} (severity: {task.get('severity', '')})"]
            if evidence:
                lines.append(f"    # evidence: {evidence}")
            if root_cause:
                lines.append(f"    # root_cause: {root_cause}")
            if fix_area:
                lines.append(f"    # fix_area: {fix_area}")
            if suggested_fix:
                lines.append(f"    # suggested_fix: {suggested_fix}")
            lines.append("    # TODO: implement fix for this violation type.")
            fix_parts.append("\n".join(lines))

    has_working = any(
        _VIOLATION_TO_FIX_BODY.get(t.get("violation_type", "")) for t in tasks
    )
    docstring_note = (
        "Known violation types have working fix bodies.\n"
        "Stub comments guide implementation of remaining types.\n"
        if has_working else
        "Review and replace pass with deterministic staging edits.\n"
    )

    body = ("\n\n".join(fix_parts) + "\n") if fix_parts else "    pass\n"
    if fix_parts and not has_working:
        body += "    pass\n"

    return (
        f'"""Generated in-house remediation scaffold for {doc_key}.\n{docstring_note}"""\n\n'
        f"TARGET_ADAPTER = {target_adapter!r}\n"
        f"REMEDIATION_TASKS = {tasks_literal}\n\n"
        f"def apply_inhouse_extension(source_path, staging_dir, converter_name):\n"
        f"{body}"
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
