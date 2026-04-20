"""Prompt and evidence construction helpers for the LLM judge."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.format_converters.tournament.source_evidence import build_source_evidence_packet

EXCERPT_CHARS_PER_ADAPTER: int = 2000  # chars sampled from each adapter output

# Chars sampled from each position: front / middle / end
_FRONT = 900
_MID = 600
_END = 500


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


def _pdf_evidence_block(label: str, pdf_path: Path) -> str:
    """Extract compact text evidence from a PDF for the audit prompt."""
    if not pdf_path.exists():
        return f"### {label}\nPDF missing: {pdf_path}"

    try:
        with fitz.open(pdf_path) as doc:
            pages = [page.get_text("text").strip() for page in doc]
    except Exception as exc:
        return f"### {label}\nPath: {pdf_path}\nUnable to read PDF evidence: {exc}"
    joined = "\n\n".join(text for text in pages if text)
    excerpt = _excerpt(joined) if joined else ""
    return (
        f"### {label}\n"
        f"Path: {pdf_path}\n"
        f"Pages: {len(pages)}\n\n"
        f"```text\n{excerpt}\n```"
    )


def _traits_summary(traits: DocumentTraits) -> str:
    """One-line summary of document traits for the judge."""
    flags = []
    if traits.is_scanned:
        flags.append("scanned/OCR")
    if traits.is_image_heavy:
        flags.append("image-heavy")
    if traits.is_table_heavy:
        flags.append("table-heavy")
    if traits.is_multi_column:
        flags.append("multi-column")
    if traits.is_text_only:
        flags.append("text-only")
    if traits.has_math:
        flags.append("contains math")
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

    evidence_blocks = "\n\n---\n\n".join(_evidence_block(r) for r in candidates)

    user = (
        f"## Source document\n{_traits_summary(traits)}\n\n"
        f"## Conversion outputs\n\n{evidence_blocks}\n\n"
        "## Task\n"
        f"Select the best conversion from: {adapter_names}.\n"
        'Return JSON with "preferred" set to exactly one of those names, and include '
        "only material violations that a coding agent should turn into tests or "
        "in-house conversion fixes."
    )

    return system, user


def build_audit_prompt(
    candidate: AdapterResult,
    source_path: Path,
    traits: DocumentTraits,
    audit_pdf_path: Path,
) -> tuple[str, str]:
    """Build a prompt that audits one selected candidate against source context."""
    system = (
        "You are an expert document-conversion quality evaluator. "
        "You will be shown one selected Markdown conversion plus source-document "
        "metadata. Audit whether this candidate appears acceptable or contains "
        "material issues that should trigger remediation work.\n\n"
        "Return ONLY valid JSON with this exact shape:\n"
        "{\n"
        '  "preferred": "<candidate_name>",\n'
        '  "confidence": "high|medium|low",\n'
        '  "reasoning": "<one paragraph>",\n'
        '  "notes": {"<candidate_name>": "<brief note>"},\n'
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
        "}\n\n"
        "If the candidate appears acceptable, return an empty violations list. "
        "Only include violations that are concrete enough for a coding agent to "
        "turn into tests or converter fixes."
    )

    user = (
        "## Source document\n"
        f"{_traits_summary(traits)}\n\n"
        "## Source evidence packet\n\n"
        f"```text\n{build_source_evidence_packet(source_path, traits).to_prompt_text()}\n```\n\n"
        "## Rendered candidate audit PDF\n\n"
        f"{_pdf_evidence_block('Rendered candidate PDF', audit_pdf_path)}\n\n"
        "## Candidate Markdown\n\n"
        f"{_evidence_block(candidate)}\n\n"
        "## Task\n"
        f"Audit candidate {candidate.method_name!r}. Return JSON with "
        f'"preferred" set to exactly "{candidate.method_name}". '
        "Compare the rendered candidate PDF against the source evidence packet first. "
        "Use the Markdown block only as supporting detail. Flag material issues only."
    )
    return system, user

