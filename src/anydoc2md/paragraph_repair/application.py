"""Paragraph continuity repair entry points.

`repair_markdown_paragraph_continuity` is the deterministic, file-I/O-free
orchestrator that composes block splitting, row-sliced detection, conservative
repair drafting, and the quality-acceptance gate into a single
`ParagraphRepairResult`. File-level staging helpers build on that in-memory
entry point while preserving raw adapter output.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import (
    MarkdownBlock,
    ParagraphRepairReport,
    ParagraphRepairResult,
    ParagraphRepairSettings,
)
from anydoc2md.paragraph_repair.quality import accept_repair
from anydoc2md.paragraph_repair.repairer import repair_blocks

INDEX_MD = "index.md"
PARAGRAPH_REPAIRED_MD = "index_paragraph_repaired.md"
PARAGRAPH_REPAIR_REPORT_JSON = "paragraph_repair_report.json"
_SIDECAR_SCHEMA_VERSION = 1
_SIDECAR_CREATED_BY = "anydoc2md.paragraph_repair"


def repair_markdown_paragraph_continuity(
    md_text: str,
    settings: ParagraphRepairSettings | None = None,
) -> ParagraphRepairResult:
    """Repair row-sliced paragraphs in memory, returning text plus evidence.

    Deterministic and side-effect free: it never reads or writes files. The
    repaired candidate text is returned only when the quality gate accepts it;
    otherwise the original text is returned unchanged with a report explaining
    why. Empty or structure-only input is handled safely and yields a rejected
    report rather than raising.
    """
    resolved = settings or ParagraphRepairSettings()
    blocks = split_markdown_blocks(md_text)
    if not resolved.enabled:
        return _disabled_result(md_text, blocks, resolved)

    draft = repair_blocks(blocks, resolved)
    decision = accept_repair(md_text, draft, resolved)

    accepted_text = draft.text if decision.accepted else md_text
    # Report counts describe the returned text, so a rejected attempt reports the
    # original paragraph count even though the draft would have merged some.
    repaired_paragraph_count = (
        draft.repaired_paragraph_count
        if decision.accepted
        else draft.original_paragraph_count
    )
    report = ParagraphRepairReport(
        attempted=True,
        accepted=decision.accepted,
        reason=decision.reason,
        original_paragraph_count=draft.original_paragraph_count,
        repaired_paragraph_count=repaired_paragraph_count,
        merge_group_count=draft.merge_group_count,
        before_score=decision.before_score,
        after_score=decision.after_score,
        signals=decision.signals,
        examples=draft.examples,
        settings=resolved,
    )
    return ParagraphRepairResult(text=accepted_text, report=report)


def _disabled_result(
    md_text: str,
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings,
) -> ParagraphRepairResult:
    """Return a no-op result when repair is disabled.

    Disabled repair must not draft merges or run the quality gate, so the report
    carries no merge evidence, scores, signals, or example snippets -- only the
    cheap original paragraph count over the already-split blocks.
    """
    original_paragraph_count = sum(1 for block in blocks if block.is_prose)
    report = ParagraphRepairReport(
        attempted=False,
        accepted=False,
        reason="disabled",
        original_paragraph_count=original_paragraph_count,
        repaired_paragraph_count=original_paragraph_count,
        merge_group_count=0,
        before_score=0.0,
        after_score=0.0,
        signals={},
        examples=[],
        settings=settings,
    )
    return ParagraphRepairResult(text=md_text, report=report)


def apply_paragraph_continuity_repair(
    adapter_name: str,
    adapter_staging_dir: Path,
    source_path: Path,
    *,
    settings: ParagraphRepairSettings | None = None,
) -> ParagraphRepairReport:
    """Apply paragraph repair to one adapter staging directory.

    The raw adapter output at `index.md` is never modified. Accepted repair is
    written to a paragraph-repair-specific artifact, not the shared
    `index_fixed.md` tournament slot. A later integration slice must decide how
    to compose that artifact with project-local fix extensions. Stale artifacts
    owned by this helper are removed before each run, including disabled or
    rejected runs, so stale paragraph-repair output cannot linger.
    """
    resolved = settings or ParagraphRepairSettings()
    if not adapter_staging_dir.is_dir():
        return _no_input_report("staging_dir_missing", resolved)

    _remove_owned_artifacts(adapter_staging_dir)
    index_md = adapter_staging_dir / INDEX_MD
    if not index_md.exists():
        return _no_input_report("index_md_missing", resolved)

    original_text = index_md.read_text(encoding="utf-8")
    result = repair_markdown_paragraph_continuity(original_text, resolved)
    if not result.report.accepted:
        return result.report

    repaired_md = adapter_staging_dir / PARAGRAPH_REPAIRED_MD
    _write_text_atomic(repaired_md, result.text)
    _write_sidecar(
        adapter_name=adapter_name,
        adapter_staging_dir=adapter_staging_dir,
        source_path=source_path,
        original_text=original_text,
        repaired_text=result.text,
        report=result.report,
    )
    return result.report


def _no_input_report(
    reason: str,
    settings: ParagraphRepairSettings,
) -> ParagraphRepairReport:
    return ParagraphRepairReport(
        attempted=False,
        accepted=False,
        reason=reason,
        original_paragraph_count=0,
        repaired_paragraph_count=0,
        merge_group_count=0,
        before_score=0.0,
        after_score=0.0,
        signals={},
        examples=[],
        settings=settings,
    )


def _remove_owned_artifacts(adapter_staging_dir: Path) -> None:
    for filename in (PARAGRAPH_REPAIRED_MD, PARAGRAPH_REPAIR_REPORT_JSON):
        path = adapter_staging_dir / filename
        if path.exists():
            path.unlink()


def _write_sidecar(
    *,
    adapter_name: str,
    adapter_staging_dir: Path,
    source_path: Path,
    original_text: str,
    repaired_text: str,
    report: ParagraphRepairReport,
) -> None:
    payload = {
        "schema_version": _SIDECAR_SCHEMA_VERSION,
        "created_by": _SIDECAR_CREATED_BY,
        "adapter_name": adapter_name,
        "source_document": {"path": _portable_source_path(source_path)},
        "adapter_staging": {"path": ".", "name": adapter_staging_dir.name},
        "input": _text_artifact(INDEX_MD, original_text),
        "output": _text_artifact(PARAGRAPH_REPAIRED_MD, repaired_text),
        "owns_output": True,
        "publishes_index_fixed": False,
        "report": report.to_dict(),
    }
    sidecar = adapter_staging_dir / PARAGRAPH_REPAIR_REPORT_JSON
    _write_text_atomic(sidecar, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _text_artifact(path: str, text: str) -> dict[str, int | str]:
    data = text.encode("utf-8")
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _portable_source_path(source_path: Path) -> str:
    if source_path.is_absolute():
        return source_path.name
    return source_path.as_posix()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(text)
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            tmp_path = Path(tmp_name)
            if tmp_path.exists():
                tmp_path.unlink()
