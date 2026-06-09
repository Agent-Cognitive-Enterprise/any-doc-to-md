"""Paragraph continuity repair entry points.

`repair_markdown_paragraph_continuity` is the deterministic, file-I/O-free
orchestrator that composes block splitting, row-sliced detection, conservative
repair drafting, and the quality-acceptance gate into a single
`ParagraphRepairResult`. File-level staging helpers build on it in a later slice.
"""
from __future__ import annotations

from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import (
    MarkdownBlock,
    ParagraphRepairReport,
    ParagraphRepairResult,
    ParagraphRepairSettings,
)
from anydoc2md.paragraph_repair.quality import accept_repair
from anydoc2md.paragraph_repair.repairer import repair_blocks


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
