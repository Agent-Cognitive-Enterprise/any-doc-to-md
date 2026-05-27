"""Data model for deterministic paragraph continuity repair."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

SignalValue: TypeAlias = float | int | str | bool


@dataclass(frozen=True)
class ParagraphRepairSettings:
    """Conservative defaults for row-sliced paragraph repair."""

    enabled: bool = True
    min_paragraphs: int = 20
    min_short_ratio: float = 0.55
    min_no_terminal_ratio: float = 0.35
    min_continuation_ratio: float = 0.35
    min_quality_delta: float = 0.75
    max_merged_paragraph_chars: int = 2500
    max_examples: int = 5
    max_example_chars: int = 160


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
