"""PyMuPDF extraction helpers for the in-house PDF converter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from anydoc2md.format_converters._pdf_blocks import (
    ImageBlock,
    TableBlock,
    TextBlock,
    block_column,
    clean_line,
    detect_block_kind,
    page_avg_font,
)
from anydoc2md.format_converters._pdf_tables import extract_page_tables
from anydoc2md.format_converters.base import IMAGES_DIRNAME

TABLE_EXTRACTION_PYMUPDF = "pymupdf"
TABLE_EXTRACTION_OFF = "off"


@dataclass(frozen=True)
class PdfExtractionResult:
    text_blocks: list[TextBlock]
    image_blocks: list[ImageBlock]
    table_blocks: list[TableBlock]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def extract_pdf_blocks(
    pdf_path: Path,
    images_dir: Path,
    *,
    column_split_ratio: float,
    min_text_len: int,
) -> tuple[list[TextBlock], list[ImageBlock]]:
    result = extract_pdf_blocks_v2(
        pdf_path,
        images_dir,
        column_split_ratio=column_split_ratio,
        min_text_len=min_text_len,
        table_extraction=TABLE_EXTRACTION_OFF,
    )
    return result.text_blocks, result.image_blocks


def extract_pdf_blocks_v2(
    pdf_path: Path,
    images_dir: Path,
    *,
    column_split_ratio: float,
    min_text_len: int,
    table_extraction: str | bool = TABLE_EXTRACTION_PYMUPDF,
    table_markdown_clean: bool = False,
    table_markdown_fill_empty: bool = True,
) -> PdfExtractionResult:
    images_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))

    text_blocks: list[TextBlock] = []
    image_blocks: list[ImageBlock] = []
    table_blocks: list[TableBlock] = []
    warnings: list[str] = []
    seen_hashes: set[str] = set()

    mode = _normalize_table_extraction_mode(table_extraction)
    if mode not in {TABLE_EXTRACTION_PYMUPDF, TABLE_EXTRACTION_OFF}:
        warnings.append(
            f"unsupported table_extraction mode {table_extraction!r}; "
            "table extraction disabled"
        )
        mode = TABLE_EXTRACTION_OFF

    try:
        for page_num, page in enumerate(doc, start=1):
            page_dict = page.get_text("dict")
            page_avg = page_avg_font(page_dict)
            page_width = page.rect.width

            text_blocks.extend(
                _extract_page_text_blocks(
                    page_dict=page_dict,
                    page_num=page_num,
                    page_avg=page_avg,
                    page_width=page_width,
                    column_split_ratio=column_split_ratio,
                    min_text_len=min_text_len,
                )
            )
            image_blocks.extend(
                _extract_page_images(
                    doc=doc,
                    page=page,
                    page_num=page_num,
                    images_dir=images_dir,
                    page_width=page_width,
                    column_split_ratio=column_split_ratio,
                    seen_hashes=seen_hashes,
                )
            )
            if mode == TABLE_EXTRACTION_PYMUPDF:
                page_tables, page_warnings = extract_page_tables(
                    page,
                    page_num=page_num,
                    page_width=page_width,
                    column_split_ratio=column_split_ratio,
                    clean=table_markdown_clean,
                    fill_empty=table_markdown_fill_empty,
                )
                table_blocks.extend(page_tables)
                warnings.extend(page_warnings)
    finally:
        doc.close()

    return PdfExtractionResult(
        text_blocks=text_blocks,
        image_blocks=image_blocks,
        table_blocks=table_blocks,
        warnings=tuple(warnings),
    )


def _normalize_table_extraction_mode(value: str | bool) -> str:
    if isinstance(value, bool):
        return TABLE_EXTRACTION_PYMUPDF if value else TABLE_EXTRACTION_OFF
    return str(value).strip().lower()


def _extract_page_text_blocks(
    *,
    page_dict: dict,
    page_num: int,
    page_avg: float,
    page_width: float,
    column_split_ratio: float,
    min_text_len: int,
) -> list[TextBlock]:
    text_blocks: list[TextBlock] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines_text: list[str] = []
        sizes: list[float] = []
        for line in block.get("lines", []):
            parts: list[str] = []
            for span in line.get("spans", []):
                text = clean_line(span.get("text", ""))
                if not text:
                    continue
                parts.append(text)
                if span.get("size"):
                    sizes.append(span["size"])
            if parts:
                lines_text.append(" ".join(parts))

        raw = "\n".join(lines_text).strip()
        if not raw or len(raw) < min_text_len:
            continue

        avg_size = sum(sizes) / len(sizes) if sizes else page_avg
        bbox = tuple(block["bbox"])
        text_blocks.append(TextBlock(
            page=page_num,
            bbox=bbox,
            text=raw,
            block_kind=detect_block_kind(raw, avg_size, page_avg),
            avg_font_size=avg_size,
            column=block_column(bbox, page_width, column_split_ratio),
        ))
    return text_blocks


def _extract_page_images(
    *,
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    images_dir: Path,
    page_width: float,
    column_split_ratio: float,
    seen_hashes: set[str],
) -> list[ImageBlock]:
    image_blocks: list[ImageBlock] = []
    for img_ref in page.get_images(full=True):
        xref = img_ref[0]
        try:
            base_image = doc.extract_image(xref)
        except Exception:
            continue
        img_bytes = base_image.get("image")
        if not img_bytes:
            continue
        img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
        if img_hash in seen_hashes:
            continue
        seen_hashes.add(img_hash)

        ext = base_image.get("ext", "png")
        filename = f"img_p{page_num:03d}_{img_hash}.{ext}"
        (images_dir / filename).write_bytes(img_bytes)

        bbox = _image_bbox(page, xref)
        image_blocks.append(ImageBlock(
            page=page_num,
            bbox=bbox,
            filename=f"{IMAGES_DIRNAME}/{filename}",
            width=base_image.get("width", 0),
            height=base_image.get("height", 0),
            page_width=page_width,
            column=block_column(bbox, page_width, column_split_ratio),
        ))
    return image_blocks


def _image_bbox(page: fitz.Page, xref: int) -> tuple[float, float, float, float]:
    for item in page.get_image_rects(xref):
        return (item.x0, item.y0, item.x1, item.y1)
    return (0.0, 0.0, page.rect.width, 0.0)
