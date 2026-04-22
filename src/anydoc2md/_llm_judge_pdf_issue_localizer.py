"""Deterministic issue localization for source-PDF vs candidate-PDF auditing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re

import fitz

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9./-]{3,}")
_DATE_LINE_RE = re.compile(r"^\d{1,2}\s+[A-Z]{3}\s+\d{4}$")
_PAGE_OF_RE = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)
_PURE_NUMBER_RE = re.compile(r"^\d+$")
_SOURCE_PATH_LINE_RE = re.compile(r"^\*\*Source:\*\*\s+file:", re.IGNORECASE)
_STOPWORDS = {
    "about", "after", "also", "been", "being", "between", "chapter", "could",
    "does", "each", "from", "have", "into", "just", "more", "must", "page",
    "should", "than", "that", "their", "them", "there", "these", "this",
    "those", "through", "under", "using", "when", "where", "which", "while",
    "with", "within", "would", "your",
}
_MAX_ANCHOR_TOKENS = 18
_MAX_ISSUE_CLUSTERS = 12
_DEFAULT_MIN_ANCHOR_COVERAGE = 0.45
_SHORT_DOC_FULL_CONTEXT_PAGES = 10
_SOURCE_CONTEXT_MARGIN_PAGES = 1
_CANDIDATE_CONTEXT_MARGIN_PAGES = 1
_MAX_SOURCE_PAGES_PER_ISSUE = 4
_MAX_CANDIDATE_PAGES_PER_ISSUE = 8
_MAX_EXCERPT_PAGES = 6
_MAX_EXCERPT_CHARS_PER_PAGE = 350
_MAX_EXCERPT_TOTAL_CHARS = 2600


@dataclass(frozen=True)
class PdfPageMatch:
    source_page: int
    candidate_page: int
    anchor_coverage: float
    matched_anchor_count: int
    anchor_count: int


@dataclass(frozen=True)
class PdfSuspectedIssue:
    issue_type: str
    description: str
    source_page_start: int
    source_page_end: int
    candidate_page_start: int
    candidate_page_end: int
    source_excerpt: str
    candidate_excerpt: str


def detect_pdf_suspected_issues(
    source_pdf_path: Path,
    candidate_pdf_path: Path,
    *,
    min_anchor_coverage: float = _DEFAULT_MIN_ANCHOR_COVERAGE,
    max_issue_clusters: int = _MAX_ISSUE_CLUSTERS,
) -> list[PdfSuspectedIssue]:
    """Return localized issue windows that deserve narrow LLM review."""
    source_pages = _load_normalized_pdf_pages(source_pdf_path)
    candidate_pages = _load_normalized_pdf_pages(candidate_pdf_path)
    if not source_pages or not candidate_pages:
        return []

    source_doc_freq = _document_frequency(source_pages)
    matches: list[PdfPageMatch] = []
    suspicious_pages: list[PdfPageMatch] = []

    search_radius = max(3, round((len(candidate_pages) / max(1, len(source_pages))) * 4))
    for source_index, source_text in enumerate(source_pages, start=1):
        anchor_tokens = _select_anchor_tokens(source_text, source_doc_freq)
        if not anchor_tokens:
            continue
        match = _best_candidate_match(
            source_page=source_index,
            source_page_count=len(source_pages),
            candidate_page_count=len(candidate_pages),
            candidate_pages=candidate_pages,
            anchor_tokens=anchor_tokens,
            search_radius=search_radius,
        )
        matches.append(match)
        if match.anchor_coverage < min_anchor_coverage:
            suspicious_pages.append(match)

    if not suspicious_pages:
        return []

    if len(source_pages) <= _SHORT_DOC_FULL_CONTEXT_PAGES:
        match_pages = [match.candidate_page for match in suspicious_pages]
        return [
            PdfSuspectedIssue(
                issue_type="suspected_content_mismatch",
                description=(
                    "Deterministic page-anchor comparison found low coverage on "
                    f"{len(suspicious_pages)} of {len(matches)} source pages "
                    f"(pages {suspicious_pages[0].source_page}-{suspicious_pages[-1].source_page})."
                ),
                source_page_start=1,
                source_page_end=len(source_pages),
                candidate_page_start=1,
                candidate_page_end=len(candidate_pages),
                source_excerpt=_format_page_excerpt(source_pages, 1, len(source_pages), "Source page"),
                candidate_excerpt=_format_page_excerpt(
                    candidate_pages,
                    1,
                    len(candidate_pages),
                    "Candidate page",
                ),
            )
        ]

    issues: list[PdfSuspectedIssue] = []
    for cluster in _split_suspicious_clusters(_cluster_suspicious_pages(suspicious_pages)):
        source_pages_in_cluster = [match.source_page for match in cluster]
        candidate_pages_in_cluster = [match.candidate_page for match in cluster]
        source_start = max(1, min(source_pages_in_cluster) - _SOURCE_CONTEXT_MARGIN_PAGES)
        source_end = min(len(source_pages), max(source_pages_in_cluster) + _SOURCE_CONTEXT_MARGIN_PAGES)
        candidate_start = max(1, min(candidate_pages_in_cluster) - _CANDIDATE_CONTEXT_MARGIN_PAGES)
        candidate_end = min(
            len(candidate_pages),
            max(candidate_pages_in_cluster) + _CANDIDATE_CONTEXT_MARGIN_PAGES,
        )
        avg_coverage = sum(match.anchor_coverage for match in cluster) / len(cluster)
        issues.append(
            PdfSuspectedIssue(
                issue_type="suspected_content_mismatch",
                description=(
                    "Deterministic page-anchor comparison found low lexical anchor coverage "
                    f"({avg_coverage:.2f}) on source pages "
                    f"{min(source_pages_in_cluster)}-{max(source_pages_in_cluster)}. "
                    "Review whether content is missing, injected, or badly reordered."
                ),
                source_page_start=source_start,
                source_page_end=source_end,
                candidate_page_start=candidate_start,
                candidate_page_end=candidate_end,
                source_excerpt=_format_page_excerpt(
                    source_pages,
                    source_start,
                    source_end,
                    "Source page",
                ),
                candidate_excerpt=_format_page_excerpt(
                    candidate_pages,
                    candidate_start,
                    candidate_end,
                    "Candidate page",
                ),
            )
        )
        if len(issues) >= max_issue_clusters:
            break
    return issues


def _load_normalized_pdf_pages(pdf_path: Path) -> list[str]:
    with fitz.open(pdf_path) as doc:
        page_lines = [_normalized_page_lines(page.get_text("text", sort=True)) for page in doc]
    repeated_lines = _repeated_short_lines(page_lines)
    return [
        _collapse_page_lines(lines, repeated_lines)
        for lines in page_lines
    ]


def _normalized_page_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if _PURE_NUMBER_RE.match(line):
            continue
        if _DATE_LINE_RE.match(line):
            continue
        if _PAGE_OF_RE.match(line):
            continue
        if _SOURCE_PATH_LINE_RE.match(line):
            continue
        lines.append(line)
    return lines


def _repeated_short_lines(page_lines: list[list[str]]) -> set[str]:
    counts: Counter[str] = Counter()
    for lines in page_lines:
        counts.update({line for line in lines if len(line) <= 120})
    return {
        line
        for line, count in counts.items()
        if count >= 3 and not line.startswith("#")
    }


def _collapse_page_lines(lines: list[str], repeated_lines: set[str]) -> str:
    filtered = [line for line in lines if line not in repeated_lines]
    return " ".join(filtered).strip()


def _document_frequency(page_texts: list[str]) -> Counter[str]:
    doc_freq: Counter[str] = Counter()
    for text in page_texts:
        doc_freq.update(set(_tokenize(text)))
    return doc_freq


def _tokenize(text: str) -> list[str]:
    return [
        token.casefold()
        for token in _TOKEN_RE.findall(text)
        if token.casefold() not in _STOPWORDS
    ]


def _select_anchor_tokens(text: str, doc_freq: Counter[str]) -> list[str]:
    unique_tokens = sorted(
        set(_tokenize(text)),
        key=lambda token: (doc_freq[token], -len(token), token),
    )
    return unique_tokens[:_MAX_ANCHOR_TOKENS]


def _best_candidate_match(
    *,
    source_page: int,
    source_page_count: int,
    candidate_page_count: int,
    candidate_pages: list[str],
    anchor_tokens: list[str],
    search_radius: int,
) -> PdfPageMatch:
    expected_page = max(1, round((source_page / max(1, source_page_count)) * candidate_page_count))
    start = max(1, expected_page - search_radius)
    end = min(candidate_page_count, expected_page + search_radius)

    best_candidate_page = start
    best_matched = -1
    best_coverage = -1.0
    for candidate_page in range(start, end + 1):
        candidate_text = candidate_pages[candidate_page - 1].casefold()
        matched = sum(1 for token in anchor_tokens if token in candidate_text)
        coverage = matched / max(1, len(anchor_tokens))
        if coverage > best_coverage or (coverage == best_coverage and matched > best_matched):
            best_candidate_page = candidate_page
            best_matched = matched
            best_coverage = coverage

    return PdfPageMatch(
        source_page=source_page,
        candidate_page=best_candidate_page,
        anchor_coverage=best_coverage,
        matched_anchor_count=best_matched,
        anchor_count=len(anchor_tokens),
    )


def _cluster_suspicious_pages(matches: list[PdfPageMatch]) -> list[list[PdfPageMatch]]:
    if not matches:
        return []
    sorted_matches = sorted(matches, key=lambda match: match.source_page)
    clusters: list[list[PdfPageMatch]] = [[sorted_matches[0]]]
    for match in sorted_matches[1:]:
        prev = clusters[-1][-1]
        if match.source_page <= prev.source_page + 2:
            clusters[-1].append(match)
        else:
            clusters.append([match])
    return clusters


def _split_suspicious_clusters(clusters: list[list[PdfPageMatch]]) -> list[list[PdfPageMatch]]:
    split_clusters: list[list[PdfPageMatch]] = []
    for cluster in clusters:
        current: list[PdfPageMatch] = []
        current_source_start = 0
        current_candidate_min = 0
        current_candidate_max = 0

        for match in cluster:
            if not current:
                current = [match]
                current_source_start = match.source_page
                current_candidate_min = match.candidate_page
                current_candidate_max = match.candidate_page
                continue

            next_candidate_min = min(current_candidate_min, match.candidate_page)
            next_candidate_max = max(current_candidate_max, match.candidate_page)
            source_span = match.source_page - current_source_start + 1
            candidate_span = next_candidate_max - next_candidate_min + 1
            if (
                source_span > _MAX_SOURCE_PAGES_PER_ISSUE
                or candidate_span > _MAX_CANDIDATE_PAGES_PER_ISSUE
            ):
                split_clusters.append(current)
                current = [match]
                current_source_start = match.source_page
                current_candidate_min = match.candidate_page
                current_candidate_max = match.candidate_page
                continue

            current.append(match)
            current_candidate_min = next_candidate_min
            current_candidate_max = next_candidate_max

        if current:
            split_clusters.append(current)
    return split_clusters


def _format_page_excerpt(
    page_texts: list[str],
    start_page: int,
    end_page: int,
    label: str,
) -> str:
    parts: list[str] = []
    total_chars = 0
    excerpt_pages = _select_excerpt_pages(start_page, end_page)
    for page_number in excerpt_pages:
        text = page_texts[page_number - 1] if page_number - 1 < len(page_texts) else ""
        excerpt = text[:_MAX_EXCERPT_CHARS_PER_PAGE]
        part = f"{label} {page_number}:\n{excerpt}"
        separator_len = 2 if parts else 0
        if total_chars + separator_len + len(part) > _MAX_EXCERPT_TOTAL_CHARS:
            break
        parts.append(part)
        total_chars += separator_len + len(part)
    if end_page - start_page + 1 > len(excerpt_pages):
        parts.append(
            f"[Selected {len(parts)} of {end_page - start_page + 1} {label.lower()}s for brevity.]"
        )
    return "\n\n".join(parts)


def _select_excerpt_pages(start_page: int, end_page: int) -> list[int]:
    page_numbers = list(range(start_page, end_page + 1))
    if len(page_numbers) <= _MAX_EXCERPT_PAGES:
        return page_numbers

    last_index = len(page_numbers) - 1
    selected = {
        page_numbers[round(index * last_index / (_MAX_EXCERPT_PAGES - 1))]
        for index in range(_MAX_EXCERPT_PAGES)
    }
    return sorted(selected)
