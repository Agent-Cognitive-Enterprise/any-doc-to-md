"""Deterministic row-sliced paragraph detector.

The detector is tuned for Markdown where visual rows became separate Markdown
paragraph blocks. It intentionally does not treat soft line breaks inside one
Markdown paragraph as broken paragraphs because that text is still one Markdown
paragraph semantically.

Some continuation signals use Latin-script punctuation and lowercase checks.
That is a lightweight heuristic, not language-independent sentence parsing.
"""
from __future__ import annotations

import re
from statistics import median

from anydoc2md.paragraph_repair.markdown_blocks import classify_line
from anydoc2md.paragraph_repair.model import (
    DetectionDecision,
    FragmentationSignals,
    MarkdownBlock,
    ParagraphRepairSettings,
)

_TERMINAL_RE = re.compile(r"""[.!?]["')\]]*$""")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_CONTINUATION_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "after",
    "although",
    "before",
    "because",
    "but",
    "by",
    "during",
    "for",
    "from",
    "if",
    "in",
    "into",
    "of",
    "or",
    "than",
    "that",
    "the",
    "though",
    "to",
    "under",
    "when",
    "whether",
    "with",
    "which",
    "while",
    "without",
}


def compute_fragmentation_signals(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings | None = None,
) -> FragmentationSignals:
    """Compute row-slicing signals over prose blocks only."""
    resolved = settings or ParagraphRepairSettings()
    prose_blocks = [block for block in blocks if block.is_prose]
    structural_count = sum(1 for block in blocks if block.is_hard_boundary)
    blank_count = sum(1 for block in blocks if block.is_blank)

    prose_texts = [_normalized_block_text(block) for block in prose_blocks]
    prose_count = len(prose_texts)
    content_count = prose_count + structural_count
    if prose_count == 0:
        return FragmentationSignals(
            prose_block_count=0,
            structural_block_count=structural_count,
            blank_block_count=blank_count,
            median_prose_chars=0.0,
            short_ratio=0.0,
            no_terminal_ratio=0.0,
            lowercase_start_ratio=0.0,
            continuation_pair_ratio=0.0,
            qualifying_continuation_run_count=0,
            longest_continuation_run=0,
            structure_ratio=_ratio(structural_count, content_count),
        )

    pair_runs = _continuation_pair_runs(blocks, resolved)
    pair_decisions = [decision for run in pair_runs for decision in run]
    run_lengths = _continuation_run_lengths(pair_runs)
    longest_run = max(run_lengths, default=0)
    qualifying_run_count = sum(
        1 for length in run_lengths if length >= resolved.min_continuation_run_blocks
    )

    return FragmentationSignals(
        prose_block_count=prose_count,
        structural_block_count=structural_count,
        blank_block_count=blank_count,
        median_prose_chars=float(median(len(text) for text in prose_texts)),
        short_ratio=_ratio(
            sum(1 for text in prose_texts if len(text) <= resolved.short_prose_chars),
            prose_count,
        ),
        no_terminal_ratio=_ratio(
            sum(1 for text in prose_texts if not ends_terminal(text)),
            prose_count,
        ),
        lowercase_start_ratio=_lowercase_after_nonterminal_ratio(blocks),
        continuation_pair_ratio=_ratio(sum(pair_decisions), len(pair_decisions)),
        qualifying_continuation_run_count=qualifying_run_count,
        longest_continuation_run=longest_run,
        structure_ratio=_ratio(structural_count, content_count),
    )


def looks_row_sliced(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings | None = None,
) -> DetectionDecision:
    """Return a conservative ordered document-level row-slicing decision."""
    resolved = settings or ParagraphRepairSettings()
    signals = compute_fragmentation_signals(blocks, resolved)

    if not resolved.enabled:
        return DetectionDecision(detected=False, reason="disabled", signals=signals)
    if signals.prose_block_count < resolved.min_paragraphs:
        return DetectionDecision(
            detected=False,
            reason="too_few_prose_blocks",
            signals=signals,
        )
    if signals.structure_ratio > resolved.max_structure_ratio:
        return DetectionDecision(
            detected=False,
            reason="structure_ratio_above_threshold",
            signals=signals,
        )
    if signals.short_ratio < resolved.min_short_ratio:
        return DetectionDecision(
            detected=False,
            reason="short_ratio_below_threshold",
            signals=signals,
        )
    if signals.no_terminal_ratio < resolved.min_no_terminal_ratio:
        return DetectionDecision(
            detected=False,
            reason="no_terminal_ratio_below_threshold",
            signals=signals,
        )
    if signals.continuation_pair_ratio < resolved.min_continuation_ratio:
        return DetectionDecision(
            detected=False,
            reason="continuation_pair_ratio_below_threshold",
            signals=signals,
        )
    if signals.lowercase_start_ratio < resolved.min_lowercase_start_ratio:
        return DetectionDecision(
            detected=False,
            reason="lowercase_start_ratio_below_threshold",
            signals=signals,
        )
    if signals.longest_continuation_run < resolved.min_continuation_run_blocks:
        return DetectionDecision(
            detected=False,
            reason="no_qualifying_continuation_run",
            signals=signals,
        )
    return DetectionDecision(
        detected=True,
        reason="row_sliced_prose_detected",
        signals=signals,
    )


def looks_like_continuation(
    left: str,
    right: str,
    settings: ParagraphRepairSettings | None = None,
) -> bool:
    """Return whether two prose snippets look like adjacent sliced rows."""
    resolved = settings or ParagraphRepairSettings()
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text or not right_text:
        return False
    if ends_terminal(left_text):
        return False
    if _is_structural_snippet(right):
        return False
    if max(len(left_text), len(right_text)) < resolved.min_continuation_chars:
        return False

    length_signals = 0
    if len(left_text) <= resolved.short_prose_chars:
        length_signals += 1
    if len(right_text) <= resolved.short_prose_chars:
        length_signals += 1
    continuation_signals = 0
    if starts_lowercase(right_text):
        continuation_signals += 1
    if ends_with_continuation_word(left_text):
        continuation_signals += 1
    if left_text.rstrip().endswith((",", ";", ":", "-", "(", "[")):
        continuation_signals += 1
    return length_signals >= 1 and continuation_signals >= 1


def ends_terminal(text: str) -> bool:
    return bool(_TERMINAL_RE.search(text.strip()))


def starts_lowercase(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and stripped[0].islower()


def ends_with_continuation_word(text: str) -> bool:
    words = _WORD_RE.findall(text.lower())
    return bool(words) and words[-1] in _CONTINUATION_WORDS


def _continuation_pair_runs(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings,
) -> list[list[bool]]:
    return [
        _pair_decisions_for_run(run, settings)
        for run in _prose_runs(blocks)
        if len(run) > 1
    ]


def _continuation_run_lengths(pair_runs: list[list[bool]]) -> list[int]:
    run_lengths: list[int] = []
    for pair_run in pair_runs:
        run_lengths.extend(_merge_like_run_lengths(pair_run))
    return run_lengths


def _pair_decisions_for_run(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings,
) -> list[bool]:
    return [
        looks_like_continuation(left.text, right.text, settings)
        for left, right in zip(blocks, blocks[1:])
    ]


def _merge_like_run_lengths(pair_decisions: list[bool]) -> list[int]:
    if not pair_decisions:
        return []

    lengths: list[int] = []
    current_length = 1
    for decision in pair_decisions:
        if decision:
            current_length += 1
            continue
        if current_length > 1:
            lengths.append(current_length)
        current_length = 1
    if current_length > 1:
        lengths.append(current_length)
    return lengths


def _normalized_block_text(block: MarkdownBlock) -> str:
    return _normalize_text(block.text)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _lowercase_after_nonterminal_ratio(blocks: list[MarkdownBlock]) -> float:
    numerator = 0
    denominator = 0
    for run in _prose_runs(blocks):
        run_numerator, run_denominator = _lowercase_pair_counts(run)
        numerator += run_numerator
        denominator += run_denominator
    return _ratio(numerator, denominator)


def _prose_runs(blocks: list[MarkdownBlock]) -> list[list[MarkdownBlock]]:
    runs: list[list[MarkdownBlock]] = []
    current_run: list[MarkdownBlock] = []
    for block in blocks:
        if block.is_prose:
            current_run.append(block)
            continue
        if block.is_blank:
            continue
        if current_run:
            runs.append(current_run)
            current_run = []
    if current_run:
        runs.append(current_run)
    return runs


def _is_structural_snippet(text: str) -> bool:
    for line in text.splitlines():
        if line.strip():
            return classify_line(line) not in {"blank", "prose"}
    return False


def _lowercase_pair_counts(blocks: list[MarkdownBlock]) -> tuple[int, int]:
    numerator = 0
    denominator = 0
    for left, right in zip(blocks, blocks[1:]):
        if ends_terminal(_normalized_block_text(left)):
            continue
        denominator += 1
        if starts_lowercase(_normalized_block_text(right)):
            numerator += 1
    return numerator, denominator


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
