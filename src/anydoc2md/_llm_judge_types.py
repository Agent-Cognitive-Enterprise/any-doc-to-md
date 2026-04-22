"""Types shared by the LLM judge helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JudgeCallResult:
    """Raw judge response plus provider-reported token usage."""

    text: str
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0

    def __iter__(self):
        """Preserve legacy `text, tokens = _call_lm_studio(...)` callers."""
        yield self.text
        yield self.tokens_used


def coerce_judge_call_result(value: JudgeCallResult | tuple[str, int]) -> JudgeCallResult:
    """Normalize legacy tuple call results into the richer usage shape."""
    if isinstance(value, JudgeCallResult):
        return value
    text, tokens_used = value
    return JudgeCallResult(text=text, tokens_used=int(tokens_used))


@dataclass(frozen=True)
class JudgeViolation:
    """Structured issue identified by the LLM judge."""

    type: str
    severity: str
    count: int = 1
    pages: list[int] = field(default_factory=list)
    confidence: float = 0.0
    evidence: str = ""
    root_cause: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "count": self.count,
            "pages": list(self.pages),
            "confidence": self.confidence,
            "evidence": self.evidence,
            "root_cause": self.root_cause,
        }


@dataclass(frozen=True)
class JudgeWindowVerdict:
    """Per-window result from a chunked PDF-to-PDF audit."""

    window_index: int
    total_windows: int
    source_page_start: int
    source_page_end: int
    candidate_page_start: int
    candidate_page_end: int
    confidence: str
    reasoning: str
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    violations: list[JudgeViolation] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "window_index": self.window_index,
            "total_windows": self.total_windows,
            "source_page_start": self.source_page_start,
            "source_page_end": self.source_page_end,
            "candidate_page_start": self.candidate_page_start,
            "candidate_page_end": self.candidate_page_end,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "tokens_used": self.tokens_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "violations": [violation.to_dict() for violation in self.violations],
            "error": self.error,
        }


@dataclass(frozen=True)
class JudgeVerdict:
    """Structured output from the LLM judge."""

    preferred_adapter: str  # winner adapter name; "" when confidence=="error"
    confidence: str  # "high" | "medium" | "low" | "error"
    reasoning: str  # prose explanation
    notes: dict[str, str]  # {adapter_name: brief_note}
    model_used: str
    tokens_used: int
    input_tokens: int = 0
    output_tokens: int = 0
    violations: list[JudgeViolation] = field(default_factory=list)
    window_verdicts: list[JudgeWindowVerdict] = field(default_factory=list)
    overall_confidence: float | None = None
    uncertainty_note: str = ""
    error: str = ""  # non-empty only on failure

    @property
    def succeeded(self) -> bool:
        return self.confidence != "error"

    def to_dict(self) -> dict:
        return {
            "preferred_adapter": self.preferred_adapter,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "notes": self.notes,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "violations": [violation.to_dict() for violation in self.violations],
            "window_verdicts": [window.to_dict() for window in self.window_verdicts],
            "overall_confidence": self.overall_confidence,
            "uncertainty_note": self.uncertainty_note,
            "error": self.error,
        }
