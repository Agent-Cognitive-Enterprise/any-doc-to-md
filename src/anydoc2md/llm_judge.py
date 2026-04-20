"""
LLM judge — break near-ties between converter adapter outputs.

When the selector flags two or more adapters as near-tied (score delta ≤
NEAR_TIE_THRESHOLD), this module sends their markdown excerpts + document
traits to an LM Studio instance and returns a structured verdict.

Context strategy:
  - Default model: qwen/qwen3.6-35b-a3b (8K context)
  - Evidence budget: ≤ EXCERPT_CHARS_PER_ADAPTER chars per adapter
  - Sampling: first + middle + end of index.md (avoids reading only the intro)
  - Total token target: < 5000 tokens (thinking + response), safely within 8K

Fallback: when the LLM call fails (network, timeout, bad JSON), the verdict
is returned with confidence="error" and an error message.  Callers should
fall back to the score-based winner.

Usage:
    from anydoc2md.llm_judge import judge_near_tie

    verdict = judge_near_tie(candidates, source_path, traits)
    if verdict.confidence != "error":
        winner = verdict.preferred_adapter
    else:
        winner = score_ranked[0].adapter_name   # score fallback
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
)

EXCERPT_CHARS_PER_ADAPTER: int = 2000  # chars sampled from each adapter output

# Chars sampled from each position: front / middle / end
_FRONT = 900
_MID = 600
_END = 500


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

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
class JudgeVerdict:
    """Structured output from the LLM judge."""

    preferred_adapter: str          # winner adapter name; "" when confidence=="error"
    confidence: str                 # "high" | "medium" | "low" | "error"
    reasoning: str                  # prose explanation
    notes: dict[str, str]           # {adapter_name: brief_note}
    model_used: str
    tokens_used: int
    violations: list[JudgeViolation] = field(default_factory=list)
    overall_confidence: float | None = None
    uncertainty_note: str = ""
    error: str = ""                 # non-empty only on failure

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
            "violations": [violation.to_dict() for violation in self.violations],
            "overall_confidence": self.overall_confidence,
            "uncertainty_note": self.uncertainty_note,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Evidence building
# ---------------------------------------------------------------------------

def _excerpt(text: str) -> str:
    """
    Return a representative excerpt: front + middle + end, each clearly labelled.
    Stays within EXCERPT_CHARS_PER_ADAPTER chars total.
    """
    n = len(text)
    if n <= EXCERPT_CHARS_PER_ADAPTER:
        return text

    front = text[:_FRONT]
    mid_start = max(_FRONT, (n // 2) - _MID // 2)
    mid = text[mid_start: mid_start + _MID]
    end = text[max(0, n - _END):]

    # Always include mid/end sections with labels when doc is long;
    # only skip if start positions overlap (very short long-text edge case)
    parts = [front]
    if mid_start > _FRONT:
        parts.append(f"\n\n[...middle of document...]\n\n{mid}")
    if n - _END > mid_start + _MID:
        parts.append(f"\n\n[...end of document...]\n\n{end}")
    return "".join(parts)


def _evidence_block(result: AdapterResult) -> str:
    """Format one adapter's evidence for the judge prompt."""
    md = result.markdown_text
    n_words = len(md.split())
    n_imgs = md.count("<img") + len(re.findall(r"!\[[^\]]*\]\([^)]+\)", md))
    n_tables = md.count("\n|")  # rough table-row count
    excerpt = _excerpt(md)

    return (
        f"### Adapter: {result.method_name}\n"
        f"Stats: {len(md):,} chars, ~{n_words:,} words, "
        f"{n_imgs} image ref(s), ~{n_tables} table row(s)\n\n"
        f"```markdown\n{excerpt}\n```"
    )


def _traits_summary(traits: DocumentTraits) -> str:
    """One-line summary of document traits for the judge."""
    flags = []
    if traits.is_scanned:       flags.append("scanned/OCR")
    if traits.is_image_heavy:   flags.append("image-heavy")
    if traits.is_table_heavy:   flags.append("table-heavy")
    if traits.is_multi_column:  flags.append("multi-column")
    if traits.is_text_only:     flags.append("text-only")
    if traits.has_math:         flags.append("contains math")
    flag_str = ", ".join(flags) if flags else "standard text document"
    return (
        f"Type: {traits.file_type.upper()} | Pages: {traits.page_count} | "
        f"Source images: {traits.image_count} | Source tables: {traits.table_count} | "
        f"Characteristics: {flag_str}"
    )


def build_prompt(
    candidates: list[AdapterResult],
    traits: DocumentTraits,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for the judge.

    Returns a tuple so callers can test prompt construction independently.
    """
    adapter_names = [r.method_name for r in candidates]

    system = (
        "You are an expert document-conversion quality evaluator. "
        "You will be shown Markdown excerpts produced by different converters "
        "from the same source document. "
        "Your task is to select the highest-quality conversion based on:\n"
        "- Text completeness and reading order\n"
        "- Table structure preservation\n"
        "- Image reference accuracy\n"
        "- Heading hierarchy and list formatting\n"
        "- Absence of garbling, duplication, or truncation\n\n"
        "Respond ONLY with a valid JSON object — no prose before or after:\n"
        "{\n"
        '  "preferred": "<adapter_name>",\n'
        '  "confidence": "high|medium|low",\n'
        '  "reasoning": "<one paragraph>",\n'
        '  "notes": {"<adapter>": "<brief note>", ...},\n'
        '  "violations": [\n'
        "    {\n"
        '      "type": "<violation_type>",\n'
        '      "severity": "critical|major|minor",\n'
        '      "count": 1,\n'
        '      "pages": [1, 2],\n'
        '      "confidence": 0.0,\n'
        '      "evidence": "<short evidence>",\n'
        '      "root_cause": "<likely root cause>"\n'
        "    }\n"
        "  ],\n"
        '  "overall_confidence": 0.0,\n'
        '  "uncertainty_note": "<optional uncertainty note>"\n'
        "}"
    )

    evidence_blocks = "\n\n---\n\n".join(
        _evidence_block(r) for r in candidates
    )

    user = (
        f"## Source document\n{_traits_summary(traits)}\n\n"
        f"## Conversion outputs\n\n{evidence_blocks}\n\n"
        f"## Task\n"
        f"Select the best conversion from: {adapter_names}.\n"
        'Return JSON with "preferred" set to exactly one of those names, and include '
        "only material violations that a coding agent should turn into tests or "
        "in-house conversion fixes."
    )

    return system, user


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_lm_studio(
    system: str,
    user: str,
    settings: JudgeSettings,
) -> tuple[str, int]:
    """
    Send a chat completion request to an OpenAI-compatible endpoint.

    Returns (response_text, tokens_used).
    Raises on network failure.
    """
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        # chat_template_kwargs disables thinking mode on Qwen3 models,
        # ensuring the JSON response lands in content (not reasoning_content).
        "chat_template_kwargs": {"thinking": False} if settings.disable_thinking else {},
    }

    resp = requests.post(
        f"{settings.url.rstrip('/')}/chat/completions",
        json=payload,
        timeout=settings.timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_violations(raw_violations: object) -> list[JudgeViolation]:
    if not isinstance(raw_violations, list):
        return []

    violations: list[JudgeViolation] = []
    for item in raw_violations:
        if not isinstance(item, dict):
            continue
        raw_pages = item.get("pages", [])
        pages = [int(page) for page in raw_pages if isinstance(page, (int, float))]
        raw_confidence = item.get("confidence", 0.0)
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.0
        raw_count = item.get("count", 1)
        count = int(raw_count) if isinstance(raw_count, (int, float)) else 1
        violations.append(
            JudgeViolation(
                type=str(item.get("type", "unknown")),
                severity=str(item.get("severity", "major")),
                count=max(1, count),
                pages=pages,
                confidence=confidence,
                evidence=str(item.get("evidence", "")),
                root_cause=str(item.get("root_cause", "")),
            )
        )
    return violations

def _parse_verdict(
    raw: str,
    candidates: list[AdapterResult],
    model: str,
    tokens: int,
) -> JudgeVerdict:
    """
    Parse the LLM JSON response into a JudgeVerdict.

    Falls back to confidence="error" if the JSON is malformed or the
    preferred adapter name doesn't match any candidate.
    """
    valid_names = {r.method_name for r in candidates}

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return JudgeVerdict(
            preferred_adapter="", confidence="error", reasoning="",
            notes={}, model_used=model, tokens_used=tokens,
            error=f"JSON parse error: {exc} — raw: {raw[:200]}",
        )

    preferred = data.get("preferred", "")
    if preferred not in valid_names:
        return JudgeVerdict(
            preferred_adapter="", confidence="error", reasoning="",
            notes={}, model_used=model, tokens_used=tokens,
            error=f"LLM returned unknown adapter {preferred!r}; expected one of {sorted(valid_names)}",
        )

    confidence = data.get("confidence", "medium")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    overall_confidence = data.get("overall_confidence")
    if not isinstance(overall_confidence, (int, float)):
        overall_confidence = None

    return JudgeVerdict(
        preferred_adapter=preferred,
        confidence=confidence,
        reasoning=data.get("reasoning", ""),
        notes=data.get("notes", {}),
        model_used=model,
        tokens_used=tokens,
        violations=_parse_violations(data.get("violations", [])),
        overall_confidence=float(overall_confidence) if overall_confidence is not None else None,
        uncertainty_note=str(data.get("uncertainty_note", "")),
        error="",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def judge_near_tie(
    candidates: list[AdapterResult],
    source_path: Path,
    traits: DocumentTraits,
    *,
    settings: JudgeSettings | None = None,
) -> JudgeVerdict:
    """
    Ask the LLM judge to select the best conversion among near-tied adapters.

    Args:
        candidates:     AdapterResults for the near-tied adapters (≥ 2).
        source_path:    Original source file path (used only for context display).
        traits:         DocumentTraits from classify_document.classify().
        settings:       Judge runtime settings. When omitted, they are read
                        from environment variables via anydoc2md.settings.

    Returns:
        JudgeVerdict.  On network/parse failure, confidence=="error" and
        preferred_adapter=="" — caller should fall back to score-based winner.
    """
    if len(candidates) < 2:
        # Trivially prefer the single candidate
        name = candidates[0].method_name if candidates else ""
        return JudgeVerdict(
            preferred_adapter=name, confidence="high",
            reasoning="Only one candidate — no judging needed.",
            notes={}, model_used="", tokens_used=0,
        )

    try:
        judge_settings = settings or load_judge_settings_from_env()
    except AnyDocToMdConfigError as exc:
        return JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="",
            tokens_used=0,
            error=str(exc),
        )

    system, user = build_prompt(candidates, traits)

    try:
        raw, tokens = _call_lm_studio(system, user, judge_settings)
    except Exception as exc:
        return JudgeVerdict(
            preferred_adapter="", confidence="error", reasoning="",
            notes={}, model_used=judge_settings.model, tokens_used=0,
            error=f"LM Studio call failed: {exc}",
        )

    return _parse_verdict(raw, candidates, judge_settings.model, tokens)
