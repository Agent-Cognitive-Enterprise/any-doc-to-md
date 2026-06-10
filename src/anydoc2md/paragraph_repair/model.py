"""Data model for deterministic paragraph continuity repair."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, TypeAlias

BlockKind: TypeAlias = Literal[
    "prose",
    "blank",
    "heading",
    "list_item",
    "table",
    "code_fence",
    "indented_code",
    "blockquote",
    "image",
    "caption",
    "horizontal_rule",
    "html",
    "front_matter",
]
SignalValue: TypeAlias = float | int | str | bool
DetectionReason: TypeAlias = Literal[
    "disabled",
    "too_few_prose_blocks",
    "structure_ratio_above_threshold",
    "short_ratio_below_threshold",
    "no_terminal_ratio_below_threshold",
    "continuation_pair_ratio_below_threshold",
    "lowercase_start_ratio_below_threshold",
    "no_qualifying_continuation_run",
    "row_sliced_prose_detected",
]
MergeReason: TypeAlias = Literal[
    "not_prose",
    "not_continuation",
    "continuation",
]
AcceptanceReason: TypeAlias = Literal[
    "accepted",
    "disabled",
    "no_merge_groups",
    "no_row_sliced_evidence",
    "structural_counts_changed",
    "content_not_preserved",
    "quality_delta_too_small",
]
JoinKind: TypeAlias = Literal["none", "space", "hyphen"]


@dataclass(frozen=True)
class MarkdownBlock:
    """One conservative Markdown block with original text preserved."""

    kind: BlockKind
    text: str
    start_line: int
    end_line: int

    @property
    def is_prose(self) -> bool:
        return self.kind == "prose"

    @property
    def is_blank(self) -> bool:
        return self.kind == "blank"

    @property
    def is_hard_boundary(self) -> bool:
        """True for kinds the merger must not merge across (excludes blanks)."""
        return self.kind not in {"prose", "blank"}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FragmentationSignals:
    """Cheap signals for likely row-sliced prose.

    `median_prose_chars` is reported for diagnostics and downstream repair
    quality scoring; the detector itself does not gate on it.
    """

    prose_block_count: int
    structural_block_count: int
    blank_block_count: int
    median_prose_chars: float
    short_ratio: float
    no_terminal_ratio: float
    lowercase_start_ratio: float
    continuation_pair_ratio: float
    qualifying_continuation_run_count: int
    longest_continuation_run: int
    structure_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class DetectionDecision:
    """Decision and evidence for row-sliced paragraph detection."""

    detected: bool
    reason: DetectionReason
    signals: FragmentationSignals

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "reason": self.reason,
            "signals": self.signals.to_dict(),
        }


@dataclass(frozen=True)
class ParagraphRepairSettings:
    """Conservative defaults for row-sliced paragraph repair."""

    enabled: bool = True
    min_paragraphs: int = 8
    min_short_ratio: float = 0.55
    min_no_terminal_ratio: float = 0.35
    min_lowercase_start_ratio: float = 0.20
    min_continuation_ratio: float = 0.35
    max_structure_ratio: float = 0.50
    short_prose_chars: int = 100
    min_continuation_chars: int = 24
    min_continuation_run_blocks: int = 4
    min_quality_delta: float = 0.75
    max_merged_paragraph_chars: int = 2500
    max_examples: int = 5
    max_example_chars: int = 160


@dataclass(frozen=True, kw_only=True)
class MergeDecision:
    """Pair-level merge decision used by the repairer."""

    merge: bool
    reason: MergeReason
    join_kind: JoinKind

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RepairDraft:
    """In-memory result of a single repair pass.

    `content_preserved` is a whitespace-insensitive character round-trip check:
    `True` means no non-whitespace character was dropped, added, or rewritten by
    the merger. A value of `False` means real content loss and the draft must
    not be accepted by downstream gates.

    `hyphen_join_count` reports how many merge joins collapsed an ambiguous
    end-of-block hyphen boundary (e.g. ``well-`` + ``known`` -> ``well-known``).
    These joins are character-preserving, so they do not flip `content_preserved`.
    No current gate consumes this count; it is surfaced as a diagnostic so a
    future quality gate or a report consumer can scrutinize these specific
    ambiguous boundaries without re-deriving them. Keeping it a separate count
    rather than folding it into `content_preserved` keeps the ambiguity signal
    orthogonal to the loss guard instead of tainting the whole draft with a
    single document-level boolean.
    """

    text: str
    merge_group_count: int
    original_paragraph_count: int
    repaired_paragraph_count: int
    content_preserved: bool
    hyphen_join_count: int = 0
    examples: list[str] = field(default_factory=list)
    settings: ParagraphRepairSettings | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "examples", bound_examples(self.examples, self.settings)
        )

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "merge_group_count": self.merge_group_count,
            "original_paragraph_count": self.original_paragraph_count,
            "repaired_paragraph_count": self.repaired_paragraph_count,
            "content_preserved": self.content_preserved,
            "hyphen_join_count": self.hyphen_join_count,
            "examples": list(self.examples),
        }


@dataclass(frozen=True, kw_only=True)
class AcceptanceDecision:
    """Quality-gate decision for one in-memory paragraph repair draft."""

    accepted: bool
    reason: AcceptanceReason
    before_score: float
    after_score: float
    quality_delta: float
    content_preserved: bool
    structural_counts_preserved: bool
    row_sliced_evidence: bool
    merge_group_count: int
    hyphen_join_count: int
    signals: dict[str, SignalValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "quality_delta": self.quality_delta,
            "content_preserved": self.content_preserved,
            "structural_counts_preserved": self.structural_counts_preserved,
            "row_sliced_evidence": self.row_sliced_evidence,
            "merge_group_count": self.merge_group_count,
            "hyphen_join_count": self.hyphen_join_count,
            "signals": dict(self.signals),
        }


@dataclass(frozen=True)
class ParagraphRepairReport:
    """Structured evidence for one paragraph repair attempt."""

    attempted: bool
    accepted: bool
    reason: str
    original_paragraph_count: int
    repaired_paragraph_count: int
    merge_group_count: int
    before_score: float
    after_score: float
    signals: dict[str, SignalValue] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    settings: ParagraphRepairSettings | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "examples", bound_examples(self.examples, self.settings)
        )

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "accepted": self.accepted,
            "reason": self.reason,
            "original_paragraph_count": self.original_paragraph_count,
            "repaired_paragraph_count": self.repaired_paragraph_count,
            "merge_group_count": self.merge_group_count,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "signals": dict(self.signals),
            "examples": list(self.examples),
        }


@dataclass(frozen=True)
class ParagraphRepairResult:
    """Markdown text plus the report explaining whether repair was accepted."""

    text: str
    report: ParagraphRepairReport

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "report": self.report.to_dict(),
        }


def bound_examples(
    examples: list[str],
    settings: ParagraphRepairSettings | None = None,
) -> list[str]:
    """Bound diagnostic snippets by count and length for safe reports."""
    resolved = settings or ParagraphRepairSettings()
    max_examples = max(0, resolved.max_examples)
    max_chars = max(0, resolved.max_example_chars)
    bounded: list[str] = []
    for example in examples[:max_examples]:
        if len(example) <= max_chars:
            bounded.append(example)
            continue
        if max_chars == 0:
            bounded.append("")
            continue
        marker = "..."[:max_chars]
        cutoff = max(0, max_chars - len(marker))
        bounded.append((example[:cutoff].rstrip() + marker)[:max_chars])
    return bounded
