"""Deterministic in-memory paragraph repair.

The repairer only joins adjacent `prose` blocks that the detector heuristics
classify as continuations. It never alters structural blocks (headings, lists,
tables, code fences, images, captions, blockquotes, HTML, front matter, or
horizontal rules) and never crosses a hard boundary. Code fence bytes are
preserved as-is.

Hyphen handling is preservation-first: when a left block ends with a hyphen
and the next block starts like a lowercase word, the hyphen is kept and the
join uses no space. This avoids corrupting real hyphenated compounds. Otherwise
the default join inserts a single space between the two block texts.
Whole-document whitespace is not normalized — only the immediate text inside
a merge group changes.
"""
from __future__ import annotations

import re

from anydoc2md.paragraph_repair.detector import looks_like_continuation
from anydoc2md.paragraph_repair.markdown_blocks import reconstruct_markdown
from anydoc2md.paragraph_repair.model import (
    JoinKind,
    MarkdownBlock,
    MergeDecision,
    ParagraphRepairSettings,
    RepairDraft,
)

_TRAILING_NEWLINE_RE = re.compile(r"(\r\n|\r|\n)$")
_WORD_FRAGMENT_LEFT_RE = re.compile(r"[a-z]-\Z")
_WORD_FRAGMENT_RIGHT_RE = re.compile(r"\A[a-z]")


def pair_is_continuation(
    left: MarkdownBlock,
    right: MarkdownBlock,
    settings: ParagraphRepairSettings | None = None,
) -> MergeDecision:
    """Return whether two adjacent prose blocks can join a merge run."""
    resolved = settings or ParagraphRepairSettings()
    if not (left.is_prose and right.is_prose):
        return MergeDecision(merge=False, reason="not_prose", join_kind="none")
    left_inner = _strip_trailing_newline(left.text)[0]
    right_inner = _strip_trailing_newline(right.text)[0]
    if not looks_like_continuation(left_inner, right_inner, resolved):
        return MergeDecision(
            merge=False, reason="not_continuation", join_kind="none"
        )
    return MergeDecision(
        merge=True,
        reason="continuation",
        join_kind=_join_kind(left_inner, right_inner),
    )


def should_merge(
    left: MarkdownBlock,
    right: MarkdownBlock,
    settings: ParagraphRepairSettings | None = None,
) -> MergeDecision:
    """Compatibility alias for pair-level continuation decisions.

    `merge=True` means the pair can participate in a merge run. `repair_blocks`
    still applies document/run-level gates such as `min_continuation_run_blocks`
    before rewriting text.
    """
    return pair_is_continuation(left, right, settings)


def repair_blocks(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings | None = None,
) -> RepairDraft:
    """Merge high-confidence continuation runs while preserving structure."""
    resolved = settings or ParagraphRepairSettings()
    original_paragraph_count = sum(1 for block in blocks if block.is_prose)
    original_text = reconstruct_markdown(blocks)

    output: list[MarkdownBlock] = []
    examples: list[str] = []
    merge_group_count = 0
    hyphen_join_count = 0
    min_group_blocks = max(2, resolved.min_continuation_run_blocks)

    index = 0
    while index < len(blocks):
        block = blocks[index]
        if not block.is_prose:
            output.append(block)
            index += 1
            continue

        group_indices, cursor = _collect_merge_group(blocks, index, resolved)
        if len(group_indices) < min_group_blocks:
            output.extend(blocks[index:cursor])
            index = cursor
            continue

        merged_block, group_hyphen_joins = _merge_group(blocks, group_indices)
        output.append(merged_block)
        merge_group_count += 1
        hyphen_join_count += group_hyphen_joins
        if len(examples) < resolved.max_examples:
            examples.append(_strip_trailing_newline(merged_block.text)[0])
        index = group_indices[-1] + 1

    repaired_paragraph_count = sum(1 for block in output if block.is_prose)
    repaired_text = reconstruct_markdown(output)
    return RepairDraft(
        text=repaired_text,
        merge_group_count=merge_group_count,
        original_paragraph_count=original_paragraph_count,
        repaired_paragraph_count=repaired_paragraph_count,
        content_preserved=_content_preserved(original_text, repaired_text),
        hyphen_join_count=hyphen_join_count,
        examples=examples,
        settings=resolved,
    )


def _collect_merge_group(
    blocks: list[MarkdownBlock],
    start_index: int,
    settings: ParagraphRepairSettings,
) -> tuple[list[int], int]:
    """Return prose-block indices forming a merge group starting at start_index."""
    group_indices = [start_index]
    projected_length = _inner_length(blocks[start_index])
    cursor = start_index + 1
    while cursor < len(blocks):
        candidate = blocks[cursor]
        if candidate.is_blank:
            cursor += 1
            continue
        if not candidate.is_prose:
            break
        decision = pair_is_continuation(
            blocks[group_indices[-1]], candidate, settings
        )
        if not decision.merge:
            break
        added = _projected_added_length(
            decision.join_kind, _inner_length(candidate)
        )
        if projected_length + added > settings.max_merged_paragraph_chars:
            break
        projected_length += added
        group_indices.append(cursor)
        cursor += 1
    return group_indices, cursor


def _merge_group(
    blocks: list[MarkdownBlock],
    group_indices: list[int],
) -> tuple[MarkdownBlock, int]:
    """Join a run of prose blocks, returning the block and its hyphen-join count.

    The join kind is recomputed here against the growing left edge. That is safe
    because every join keeps the right block's text intact, so the right edge of
    `merged_inner` always equals the right edge of the most recently joined
    block -- the same input `pair_is_continuation` used for its projection.
    """
    parts = [blocks[index] for index in group_indices]
    merged_inner, _ = _strip_trailing_newline(parts[0].text)
    hyphen_joins = 0
    for nxt in parts[1:]:
        right_inner, _ = _strip_trailing_newline(nxt.text)
        if _join_kind(merged_inner, right_inner) == "hyphen":
            hyphen_joins += 1
        merged_inner = _join_pair(merged_inner, right_inner)
    _, ending = _strip_trailing_newline(parts[-1].text)
    merged = MarkdownBlock(
        kind="prose",
        text=merged_inner + ending,
        start_line=parts[0].start_line,
        end_line=parts[-1].end_line,
    )
    return merged, hyphen_joins


def _join_pair(left: str, right: str) -> str:
    if _join_kind(left, right) == "hyphen":
        return left + right
    return left + " " + right


def _join_kind(left: str, right: str) -> JoinKind:
    if _looks_like_word_fragment_break(left, right):
        return "hyphen"
    return "space"


def _looks_like_word_fragment_break(left: str, right: str) -> bool:
    if not _WORD_FRAGMENT_LEFT_RE.search(left):
        return False
    if not _WORD_FRAGMENT_RIGHT_RE.match(right):
        return False
    first_word = re.match(r"[A-Za-z][A-Za-z'-]*", right)
    if first_word is None:
        return False
    return "-" not in first_word.group(0)


def _projected_added_length(join_kind: JoinKind, right_length: int) -> int:
    if join_kind == "hyphen":
        return right_length
    return right_length + 1


def _inner_length(block: MarkdownBlock) -> int:
    return len(_strip_trailing_newline(block.text)[0])


def _strip_trailing_newline(text: str) -> tuple[str, str]:
    match = _TRAILING_NEWLINE_RE.search(text)
    if match is None:
        return text, ""
    return text[: match.start()], match.group(0)


def _content_preserved(original: str, repaired: str) -> bool:
    """Return whether no non-whitespace character was dropped, added, or rewritten.

    Whitespace is ignored because the merger deliberately rewrites blank-line and
    space boundaries. Hyphen joins are character-preserving (``well-`` + ``known``
    -> ``well-known``), so they keep this `True`; the ambiguity they introduce is
    reported separately via `RepairDraft.hyphen_join_count`. A `False` here means
    real content loss, such as the old hyphen-dropping bug.
    """
    return _strip_whitespace(original) == _strip_whitespace(repaired)


def _strip_whitespace(text: str) -> str:
    return "".join(text.split())
