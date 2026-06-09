"""Quality scoring and acceptance gate for paragraph continuity repair."""
from __future__ import annotations

from anydoc2md.paragraph_repair.detector import (
    compute_fragmentation_signals,
    ends_terminal,
    looks_row_sliced,
)
from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import (
    AcceptanceDecision,
    DetectionDecision,
    FragmentationSignals,
    MarkdownBlock,
    ParagraphRepairSettings,
    RepairDraft,
    SignalValue,
)
from anydoc2md.paragraph_repair.normalization import (
    collapse_whitespace,
    strip_whitespace,
)

# These weights rank before/after paragraph continuity. Hard safety comes from
# the detector, content fingerprint, and structural-count gates below.
_SHORT_FRAGMENT_PENALTY = 6.0
_NO_TERMINAL_PENALTY = 4.0
_CONTINUATION_PAIR_PENALTY = 5.0
_QUALIFYING_RUN_PENALTY = 2.0
_LONGEST_RUN_BLOCK_PENALTY = 0.3
_COMPLETE_TERMINAL_BONUS = 2.0
_NONTERMINAL_TEXT_PENALTY = 1.5
_LONG_PROSE_BONUS = 2.0
_SHORT_PROSE_PENALTY = 2.0
_RUNAWAY_PARAGRAPH_PENALTY = 6.0
_RUNAWAY_PARAGRAPH_OVERFLOW_DIVISOR = 250.0


def score_paragraph_quality(
    blocks: list[MarkdownBlock],
    settings: ParagraphRepairSettings | None = None,
) -> float:
    """Return a deterministic paragraph-continuity quality score.

    Higher is better. The score is intentionally local and heuristic: it
    rewards complete prose paragraphs and penalizes tiny nonterminal fragments,
    continuation-like runs, and runaway paragraph lengths.
    """
    resolved = settings or ParagraphRepairSettings()
    signals = compute_fragmentation_signals(blocks, resolved)
    return _score_from_signals(blocks, signals, resolved)


def normalized_content_fingerprint(md_text: str) -> str:
    """Return a whitespace-insensitive content fingerprint for loss checks."""
    return strip_whitespace(md_text)


def accept_repair(
    original_text: str,
    draft: RepairDraft,
    settings: ParagraphRepairSettings | None = None,
) -> AcceptanceDecision:
    """Accept only score-improving, content-preserving repair drafts."""
    resolved = settings or ParagraphRepairSettings()
    original_blocks = split_markdown_blocks(original_text)
    candidate_blocks = split_markdown_blocks(draft.text)
    original_decision = looks_row_sliced(original_blocks, resolved)
    original_signals = original_decision.signals
    before_score = _score_from_signals(
        original_blocks, original_signals, resolved
    )
    after_score = score_paragraph_quality(candidate_blocks, resolved)
    quality_delta = round(after_score - before_score, 6)

    row_sliced_evidence = original_decision.detected
    structural_counts_preserved = (
        _structural_counts(original_blocks) == _structural_counts(candidate_blocks)
    )
    content_preserved = (
        draft.content_preserved
        and normalized_content_fingerprint(original_text)
        == normalized_content_fingerprint(draft.text)
    )
    signals = _decision_signals(original_decision)

    if not resolved.enabled:
        reason = "disabled"
    elif draft.merge_group_count <= 0:
        reason = "no_merge_groups"
    elif not row_sliced_evidence:
        reason = "no_row_sliced_evidence"
    elif not structural_counts_preserved:
        reason = "structural_counts_changed"
    elif not content_preserved:
        reason = "content_not_preserved"
    elif quality_delta <= resolved.min_quality_delta:
        reason = "quality_delta_too_small"
    else:
        reason = "accepted"

    return AcceptanceDecision(
        accepted=reason == "accepted",
        reason=reason,
        before_score=before_score,
        after_score=after_score,
        quality_delta=quality_delta,
        content_preserved=content_preserved,
        structural_counts_preserved=structural_counts_preserved,
        row_sliced_evidence=row_sliced_evidence,
        merge_group_count=draft.merge_group_count,
        hyphen_join_count=draft.hyphen_join_count,
        signals=signals,
    )


def _score_from_signals(
    blocks: list[MarkdownBlock],
    signals: FragmentationSignals,
    settings: ParagraphRepairSettings,
) -> float:
    prose_texts = _prose_texts(blocks)
    if not prose_texts:
        return 0.0

    score = 0.0
    for text in prose_texts:
        score += _score_prose_text(text, settings)

    score -= signals.short_ratio * _SHORT_FRAGMENT_PENALTY
    score -= signals.no_terminal_ratio * _NO_TERMINAL_PENALTY
    score -= signals.continuation_pair_ratio * _CONTINUATION_PAIR_PENALTY
    score -= signals.qualifying_continuation_run_count * _QUALIFYING_RUN_PENALTY
    score -= (
        max(0, signals.longest_continuation_run - 1)
        * _LONGEST_RUN_BLOCK_PENALTY
    )

    avg_length = sum(len(text) for text in prose_texts) / len(prose_texts)
    if settings.short_prose_chars < avg_length <= settings.max_merged_paragraph_chars:
        score += _LONG_PROSE_BONUS
    return round(score, 6)


def _score_prose_text(
    text: str,
    settings: ParagraphRepairSettings,
) -> float:
    length = len(text)
    score = 0.0
    if ends_terminal(text):
        score += _COMPLETE_TERMINAL_BONUS
    else:
        score -= _NONTERMINAL_TEXT_PENALTY

    if length <= settings.short_prose_chars:
        score -= _SHORT_PROSE_PENALTY
    else:
        score += _LONG_PROSE_BONUS

    if length > settings.max_merged_paragraph_chars:
        overflow = length - settings.max_merged_paragraph_chars
        score -= (
            _RUNAWAY_PARAGRAPH_PENALTY
            + overflow / _RUNAWAY_PARAGRAPH_OVERFLOW_DIVISOR
        )
    return score


def _prose_texts(blocks: list[MarkdownBlock]) -> list[str]:
    """Return non-empty, whitespace-collapsed text for each prose block."""
    texts = (collapse_whitespace(block.text) for block in blocks if block.is_prose)
    return [text for text in texts if text]


def _decision_signals(
    decision: DetectionDecision,
) -> dict[str, SignalValue]:
    payload = decision.signals.to_dict()
    payload["detected"] = decision.detected
    payload["detection_reason"] = decision.reason
    return payload


def _structural_counts(blocks: list[MarkdownBlock]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        if not block.is_hard_boundary:
            continue
        counts[block.kind] = counts.get(block.kind, 0) + 1
    return counts
