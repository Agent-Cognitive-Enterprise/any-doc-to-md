"""
Build compact source-side evidence packets for ADTM auditing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import fitz

from anydoc2md.format_converters.classification.classify_document import DocumentTraits

MAX_SOURCE_PAGES = 8
MAX_BLOCKS_PER_PAGE = 6
MAX_TEXT_CHUNKS = 10
MAX_CHARS_PER_BLOCK = 240


@dataclass(frozen=True)
class SourceEvidenceBlock:
    page_number: int
    block_index: int
    kind: str
    bbox: tuple[float, float, float, float] | None
    text_excerpt: str

    def to_prompt_line(self) -> str:
        bbox = ""
        if self.bbox is not None:
            bbox = (
                f" bbox=({self.bbox[0]:.0f},{self.bbox[1]:.0f},"
                f"{self.bbox[2]:.0f},{self.bbox[3]:.0f})"
            )
        return (
            f"- block {self.block_index} [{self.kind}]{bbox}: "
            f"{self.text_excerpt}"
        )


@dataclass(frozen=True)
class SourceEvidencePage:
    page_number: int
    text_excerpt: str
    blocks: list[SourceEvidenceBlock] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        lines = [f"Page {self.page_number}: {self.text_excerpt}"]
        lines.extend(block.to_prompt_line() for block in self.blocks)
        return "\n".join(lines)


@dataclass(frozen=True)
class SourceEvidencePacket:
    source_path: str
    source_kind: str
    traits_summary: str
    pages: list[SourceEvidencePage] = field(default_factory=list)
    text_chunks: list[str] = field(default_factory=list)
    note: str = ""

    def to_prompt_text(self) -> str:
        header = [
            f"Source kind: {self.source_kind}",
            f"Path: {self.source_path}",
            self.traits_summary,
        ]
        if self.note:
            header.append(f"Note: {self.note}")

        sections = ["\n".join(header)]
        if self.pages:
            sections.append(
                "Page-oriented source evidence:\n" +
                "\n\n".join(page.to_prompt_text() for page in self.pages)
            )
        if self.text_chunks:
            sections.append(
                "Text chunks:\n" +
                "\n".join(f"- {chunk}" for chunk in self.text_chunks)
            )
        return "\n\n".join(sections)


def build_source_evidence_packet(source_path: Path, traits: DocumentTraits) -> SourceEvidencePacket:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return _build_pdf_packet(source_path, traits)
    return _build_text_packet(source_path, traits)


def _build_pdf_packet(source_path: Path, traits: DocumentTraits) -> SourceEvidencePacket:
    try:
        with fitz.open(source_path) as doc:
            pages: list[SourceEvidencePage] = []
            sampled_indices = _sample_page_indices(len(doc), MAX_SOURCE_PAGES)
            for page_zero_index in sampled_indices:
                page_index = page_zero_index + 1
                page = doc[page_zero_index]
                page_text = _normalize(page.get_text("text"))
                blocks = _extract_blocks(page, page_index)
                pages.append(
                    SourceEvidencePage(
                        page_number=page_index,
                        text_excerpt=_trim(page_text),
                        blocks=blocks,
                    )
                )
    except Exception as exc:
        return SourceEvidencePacket(
            source_path=str(source_path),
            source_kind="pdf",
            traits_summary=_traits_summary_line(traits),
            note=f"Unable to build PDF evidence packet: {exc}",
        )

    return SourceEvidencePacket(
        source_path=str(source_path),
        source_kind="pdf",
        traits_summary=_traits_summary_line(traits),
        pages=pages,
    )


def _build_text_packet(source_path: Path, traits: DocumentTraits) -> SourceEvidencePacket:
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return SourceEvidencePacket(
            source_path=str(source_path),
            source_kind=traits.file_type or "text",
            traits_summary=_traits_summary_line(traits),
            note=f"Unable to extract text directly: {exc}",
        )

    parts = [
        _normalize(part)
        for part in re.split(r"\n\s*\n", text)
        if part.strip()
    ]
    sampled_indices = _sample_page_indices(len(parts), MAX_TEXT_CHUNKS)
    chunks = [_trim(parts[index]) for index in sampled_indices]
    return SourceEvidencePacket(
        source_path=str(source_path),
        source_kind=traits.file_type or "text",
        traits_summary=_traits_summary_line(traits),
        text_chunks=chunks,
    )


def _extract_blocks(page: fitz.Page, page_number: int) -> list[SourceEvidenceBlock]:
    raw_blocks = page.get_text("blocks") or []
    parsed: list[tuple[float, float, tuple[float, float, float, float], str, str]] = []
    for raw_block in raw_blocks:
        x0, y0, x1, y1, text, block_no, block_type = raw_block[:7]
        kind = "text" if block_type == 0 else "image"
        excerpt = _trim(_normalize(text) if isinstance(text, str) else kind)
        if kind == "text" and not excerpt:
            continue
        parsed.append((y0, x0, (x0, y0, x1, y1), kind, excerpt))

    # Sort blocks top-to-bottom, left-to-right for stable sampling.
    parsed.sort(key=lambda item: (item[0], item[1]))

    sampled_indices = _sample_page_indices(len(parsed), MAX_BLOCKS_PER_PAGE)
    blocks: list[SourceEvidenceBlock] = []
    for sampled_pos, index in enumerate(sampled_indices, start=1):
        _, _, bbox, kind, excerpt = parsed[index]
        blocks.append(
            SourceEvidenceBlock(
                page_number=page_number,
                block_index=sampled_pos,
                kind=kind,
                bbox=bbox,
                text_excerpt=excerpt,
            )
        )
    return blocks


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _trim(text: str) -> str:
    if len(text) <= MAX_CHARS_PER_BLOCK:
        return text
    return text[: MAX_CHARS_PER_BLOCK - 3] + "..."


def _traits_summary_line(traits: DocumentTraits) -> str:
    flags = []
    if traits.is_scanned:
        flags.append("scanned/OCR")
    if traits.is_multi_column:
        flags.append("multi-column")
    if traits.is_table_heavy:
        flags.append("table-heavy")
    if traits.is_image_heavy:
        flags.append("image-heavy")
    if traits.has_math:
        flags.append("contains math")
    joined = ", ".join(flags) if flags else "standard text document"
    return (
        f"Type={traits.file_type.upper()} pages={traits.page_count} "
        f"images={traits.image_count} tables={traits.table_count} traits={joined}"
    )


def _sample_page_indices(total: int, limit: int) -> list[int]:
    """Sample first, middle, and end indices in stable ascending order."""
    if total <= 0 or limit <= 0:
        return []
    if total <= limit:
        return list(range(total))

    if limit == 1:
        return [0]

    raw_positions = [round(step * (total - 1) / (limit - 1)) for step in range(limit)]
    indices: list[int] = []
    seen: set[int] = set()
    for index in raw_positions:
        if index not in seen:
            indices.append(index)
            seen.add(index)

    if len(indices) < limit:
        for index in range(total):
            if index not in seen:
                indices.append(index)
                seen.add(index)
            if len(indices) == limit:
                break

    return sorted(indices[:limit])
