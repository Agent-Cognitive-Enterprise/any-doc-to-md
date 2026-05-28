"""Internal paragraph continuity repair models and helpers."""
from __future__ import annotations

from anydoc2md.paragraph_repair.detector import (
    compute_fragmentation_signals,
    ends_terminal,
    ends_with_continuation_word,
    looks_like_continuation,
    looks_row_sliced,
    starts_lowercase,
)
from anydoc2md.paragraph_repair.markdown_blocks import (
    classify_line,
    reconstruct_markdown,
    split_markdown_blocks,
)
from anydoc2md.paragraph_repair.model import (
    DetectionDecision,
    FragmentationSignals,
    MarkdownBlock,
    ParagraphRepairReport,
    ParagraphRepairResult,
    ParagraphRepairSettings,
    bound_examples,
)

__all__ = [
    "DetectionDecision",
    "FragmentationSignals",
    "MarkdownBlock",
    "ParagraphRepairReport",
    "ParagraphRepairResult",
    "ParagraphRepairSettings",
    "bound_examples",
    "classify_line",
    "compute_fragmentation_signals",
    "ends_terminal",
    "ends_with_continuation_word",
    "looks_like_continuation",
    "looks_row_sliced",
    "reconstruct_markdown",
    "split_markdown_blocks",
    "starts_lowercase",
]
