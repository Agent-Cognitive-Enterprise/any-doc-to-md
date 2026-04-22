"""Page-window planning and prompt construction for PDF-to-PDF audits."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re

import fitz

from anydoc2md.format_converters.classification.classify_document import DocumentTraits

PDF_AUDIT_WINDOW_PAGES = 6
PDF_AUDIT_CANDIDATE_MARGIN_PAGES = 2
PDF_AUDIT_PAGE_TEXT_CHARS = 500
_PAGE_FRONT_CHARS = 240
_PAGE_MIDDLE_CHARS = 120
_PAGE_END_CHARS = 140


@dataclass(frozen=True)
class PdfAuditWindow:
    window_index: int
    total_windows: int
    source_page_start: int
    source_page_end: int
    source_page_count: int
    candidate_page_start: int
    candidate_page_end: int
    candidate_page_count: int
    source_excerpt: str
    candidate_excerpt: str


def build_pdf_audit_windows(
    source_pdf_path: Path,
    candidate_pdf_path: Path,
    *,
    window_pages: int = PDF_AUDIT_WINDOW_PAGES,
    candidate_margin_pages: int = PDF_AUDIT_CANDIDATE_MARGIN_PAGES,
) -> list[PdfAuditWindow]:
    """Build aligned source/candidate PDF windows for chunked LLM auditing."""
    source_pages = _extract_pdf_pages(source_pdf_path)
    candidate_pages = _extract_pdf_pages(candidate_pdf_path)
    if not source_pages or not candidate_pages:
        return []

    source_ranges = _build_ranges(len(source_pages), window_pages)
    total_windows = len(source_ranges)
    windows: list[PdfAuditWindow] = []
    for index, (source_start, source_end) in enumerate(source_ranges, start=1):
        candidate_start, candidate_end = _map_source_range_to_candidate(
            source_start=source_start,
            source_end=source_end,
            source_page_count=len(source_pages),
            candidate_page_count=len(candidate_pages),
            candidate_margin_pages=candidate_margin_pages,
        )
        windows.append(
            PdfAuditWindow(
                window_index=index,
                total_windows=total_windows,
                source_page_start=source_start,
                source_page_end=source_end,
                source_page_count=len(source_pages),
                candidate_page_start=candidate_start,
                candidate_page_end=candidate_end,
                candidate_page_count=len(candidate_pages),
                source_excerpt=_format_window_excerpt(
                    source_pages,
                    start_page=source_start,
                    end_page=source_end,
                    label="Source page",
                ),
                candidate_excerpt=_format_window_excerpt(
                    candidate_pages,
                    start_page=candidate_start,
                    end_page=candidate_end,
                    label="Candidate page",
                ),
            )
        )
    return windows


def build_windowed_audit_prompt(
    candidate_name: str,
    traits: DocumentTraits,
    window: PdfAuditWindow,
) -> tuple[str, str]:
    """Build a prompt for auditing one PDF window of the selected candidate."""
    system = (
        "You are an expert document-conversion quality evaluator. "
        "You will compare one window from the source PDF against the matching "
        "window from the rendered candidate PDF.\n\n"
        "Important constraints:\n"
        "- The candidate PDF is a reflowed audit render of Markdown, not a pagination-faithful copy.\n"
        "- Do NOT treat different page counts, different line breaks, different paragraph wrapping, "
        "or nearby within-window page shifts as issues by themselves.\n"
        "- Content may move to a nearby candidate page inside this window; check the whole candidate "
        "window before claiming missing or injected content.\n"
        "- Ignore source-path boilerplate, repeated running headers/footers, and minor numbering drift "
        "caused by reflow unless they create a real semantic error.\n"
        "- Only report concrete, high-signal issues a coding agent could act on: true content loss, "
        "material text injection, wrong figure/caption association, broken tables, or severe ordering corruption.\n\n"
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
        '      "pages": [12, 13],\n'
        '      "confidence": 0.0,\n'
        '      "evidence": "<short evidence>",\n'
        '      "root_cause": "<likely root cause>"\n'
        "    }\n"
        "  ],\n"
        '  "overall_confidence": 0.0,\n'
        '  "uncertainty_note": "<optional uncertainty note>"\n'
        "}\n\n"
        "This is one window of a longer audit. Use absolute SOURCE page numbers "
        "only in the pages field. If the candidate looks acceptable in this "
        "window, return an empty violations list."
    )

    traits_summary = (
        f"Type: {traits.file_type.upper()} | Pages: {traits.page_count} | "
        f"Source images: {traits.image_count} | Source tables: {traits.table_count}"
    )
    user = (
        f"## Source document\n{traits_summary}\n\n"
        f"## Audit window {window.window_index}/{window.total_windows}\n"
        f"Source pages: {window.source_page_start}-{window.source_page_end} "
        f"of {window.source_page_count}\n"
        f"Candidate pages: {window.candidate_page_start}-{window.candidate_page_end} "
        f"of {window.candidate_page_count}\n\n"
        "## Source PDF window\n\n"
        f"```text\n{window.source_excerpt}\n```\n\n"
        "## Rendered candidate PDF window\n\n"
        f"```text\n{window.candidate_excerpt}\n```\n\n"
        "## Task\n"
        f"Audit candidate {candidate_name!r}. Compare the rendered candidate PDF "
        "against the source PDF window. Evaluate semantic fidelity across the full "
        "candidate window, not page-for-page visual alignment. Report only material "
        "issues visible in this window that a coding agent could turn into tests "
        "or converter fixes. If the source content is present with reflowed layout, "
        "return no issue. "
        f'Set "preferred" to exactly "{candidate_name}".'
    )
    return system, user


def _extract_pdf_pages(pdf_path: Path) -> list[str]:
    with fitz.open(pdf_path) as doc:
        return [_normalize_text(page.get_text("text")) for page in doc]


def _build_ranges(page_count: int, window_pages: int) -> list[tuple[int, int]]:
    if page_count <= 0:
        return []
    return [
        (start, min(page_count, start + window_pages - 1))
        for start in range(1, page_count + 1, max(1, window_pages))
    ]


def _map_source_range_to_candidate(
    *,
    source_start: int,
    source_end: int,
    source_page_count: int,
    candidate_page_count: int,
    candidate_margin_pages: int,
) -> tuple[int, int]:
    source_start_ratio = (source_start - 1) / max(1, source_page_count)
    source_end_ratio = source_end / max(1, source_page_count)
    candidate_start = int(math.floor(source_start_ratio * candidate_page_count)) + 1
    candidate_end = int(math.ceil(source_end_ratio * candidate_page_count))
    candidate_start = max(1, candidate_start - candidate_margin_pages)
    candidate_end = min(candidate_page_count, max(candidate_start, candidate_end + candidate_margin_pages))
    return candidate_start, candidate_end


def _format_window_excerpt(
    page_texts: list[str],
    *,
    start_page: int,
    end_page: int,
    label: str,
) -> str:
    parts: list[str] = []
    for page_number in range(start_page, end_page + 1):
        text = page_texts[page_number - 1] if page_number - 1 < len(page_texts) else ""
        parts.append(f"{label} {page_number}:\n{_clip_page_text(text)}")
    return "\n\n".join(parts)


def _clip_page_text(text: str) -> str:
    if len(text) <= PDF_AUDIT_PAGE_TEXT_CHARS:
        return text
    front = text[:_PAGE_FRONT_CHARS]
    mid_start = max(_PAGE_FRONT_CHARS, (len(text) // 2) - (_PAGE_MIDDLE_CHARS // 2))
    middle = text[mid_start: mid_start + _PAGE_MIDDLE_CHARS]
    end = text[-_PAGE_END_CHARS:]
    return (
        f"{front}\n\n[...middle of page...]\n\n{middle}\n\n"
        f"[...end of page...]\n\n{end}"
    )


def _normalize_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed or "[no extractable text]"
