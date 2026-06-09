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


def paragraph_repair_candidate_is_current(adapter_staging_dir: Path) -> bool:
    """Return True iff a trusted, intact current-run paragraph-repair candidate exists.

    A candidate is trusted only when `index_paragraph_repaired.md`, a well-formed
    `paragraph_repair_report.json` written by this helper, and `index.md` are all
    present and the sidecar's recorded fingerprints both verify: the recorded raw
    input SHA-256 matches the current `index.md` (the candidate is for this run's
    input) and the recorded output SHA-256 matches the on-disk
    `index_paragraph_repaired.md` (the candidate is intact and unmodified). Any
    missing file, foreign or malformed sidecar, raw-input mismatch, or
    output-integrity mismatch is untrusted. Callers use this to decide whether a
    paragraph-repair candidate may survive staging hygiene or be composed into
    published output; it never writes anything.
    """
    repaired = adapter_staging_dir / PARAGRAPH_REPAIRED_MD
    sidecar = adapter_staging_dir / PARAGRAPH_REPAIR_REPORT_JSON
    index_md = adapter_staging_dir / INDEX_MD
    if not (repaired.is_file() and sidecar.is_file() and index_md.is_file()):
        return False
    recorded = _recorded_artifact_hashes(sidecar)
    if recorded is None:
        return False
    recorded_input_sha256, recorded_output_sha256 = recorded
    return (
        recorded_input_sha256 == _sha256_file(index_md)
        and recorded_output_sha256 == _sha256_file(repaired)
    )


def _recorded_artifact_hashes(sidecar: Path) -> tuple[str, str] | None:
    """Return (input_sha256, output_sha256) from a sidecar this helper can vouch for.

    Returns None for any sidecar this helper cannot trust: unreadable or non-JSON
    content, a non-object payload, a `created_by` that is not this helper, or an
    `input`/`output` artifact whose recorded `path` is unexpected or whose
    `sha256` is missing or not a string.
    """
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("created_by") != _SIDECAR_CREATED_BY:
        return None
    input_sha256 = _artifact_sha256(payload.get("input"), INDEX_MD)
    output_sha256 = _artifact_sha256(payload.get("output"), PARAGRAPH_REPAIRED_MD)
    if input_sha256 is None or output_sha256 is None:
        return None
    return input_sha256, output_sha256


def _artifact_sha256(artifact: object, expected_path: str) -> str | None:
    """Return a recorded artifact's sha256 when its path matches, else None."""
    if not isinstance(artifact, dict):
        return None
    if artifact.get("path") != expected_path:
        return None
    sha256 = artifact.get("sha256")
    return sha256 if isinstance(sha256, str) else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
