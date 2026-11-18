"""PyMuPDF extraction helpers for the in-house PDF converter."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import fitz

from anydoc2md.format_converters._pdf_blocks import (
    ImageBlock,
    TextBlock,
    block_column,
    clean_line,
    detect_block_kind,
    page_avg_font,
)
from anydoc2md.format_converters.base import IMAGES_DIRNAME


def extract_pdf_blocks(
    pdf_path: Path,
    images_dir: Path,
    *,
    column_split_ratio: float,
    min_text_len: int,
) -> tuple[list[TextBlock], list[ImageBlock], list[dict]]:
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir.parent / "skipped-images.json").write_text("[]\n", encoding="utf-8")
    doc = fitz.open(str(pdf_path))

    text_blocks: list[TextBlock] = []
    image_blocks: list[ImageBlock] = []
    seen_hashes: set[str] = set()
    short_blocks: list[dict] = []

    for page_num, page in enumerate(doc, start=1):
        page_dict = page.get_text("dict")
        page_avg = page_avg_font(page_dict)
        page_width = page.rect.width

        page_text = _extract_page_text_blocks(
                page_dict=page_dict,
                page_num=page_num,
                page_avg=page_avg,
                page_width=page_width,
                column_split_ratio=column_split_ratio,
                min_text_len=1,
                page_height=page.rect.height,
            )
        for block in page_text:
            reason = None
            if len(block.text) < min_text_len:
                reason = "below min_text_len"
            elif block.text in {".", "\u2022", "\u00b7", "\u2026"}:
                reason = "isolated decorative punctuation"
            if reason:
                short_blocks.append({
                    "page": block.page, "bbox": list(block.bbox), "text": block.text,
                    "reason": reason, "threshold": min_text_len,
                })
            else:
                text_blocks.append(block)
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

    doc.close()
    return text_blocks, image_blocks, short_blocks


def _extract_page_text_blocks(
    *,
    page_dict: dict,
    page_num: int,
    page_avg: float,
    page_width: float,
    column_split_ratio: float,
    min_text_len: int,
    page_height: float = 0,
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
            page_height=page_height,
            page_width=page_width,
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
        except Exception as exc:
            _record_skipped_image(images_dir, page_num, xref, str(exc))
            continue
        img_bytes = base_image.get("image")
        if not img_bytes:
            continue
        ext = base_image.get("ext", "png").lower()
        if ext not in {"png", "jpg", "jpeg", "gif", "webp"}:
            # Browsers cannot display PDF-native codecs such as JPEG 2000.
            try:
                pixmap = fitz.Pixmap(img_bytes)
                if pixmap.colorspace and pixmap.colorspace.n > 3:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                img_bytes = pixmap.tobytes("png")
            except Exception as exc:
                _record_skipped_image(images_dir, page_num, xref, str(exc))
                logging.getLogger(__name__).warning(
                    "Skipping PDF image page=%s xref=%s codec=%s: %s",
                    page_num, xref, ext, exc,
                )
                continue
            ext = "png"
        img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
        if img_hash in seen_hashes:
            continue
        seen_hashes.add(img_hash)

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


def _record_skipped_image(images_dir: Path, page: int, xref: int, reason: str) -> None:
    path = images_dir.parent / "skipped-images.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    rows.append({"page": page, "xref": xref, "reason": reason})
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _image_bbox(page: fitz.Page, xref: int) -> tuple[float, float, float, float]:
    for item in page.get_image_rects(xref):
        return (item.x0, item.y0, item.x1, item.y1)
    return (0.0, 0.0, page.rect.width, 0.0)
