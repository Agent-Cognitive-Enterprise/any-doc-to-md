"""
PDF → Markdown converter.

Extracts text blocks and images from a PDF using PyMuPDF, handles multi-column
layout, attaches figure captions to their images, filters running page headers,
and writes index.md + images/ to the staging directory.

Overrides (via document.override.yaml or explicit dict):
    column_split_ratio      float   0.55   x > page_width * ratio → right column
    min_text_len            int     10     discard blocks shorter than this
    running_header_min_pages int    3      heading on ≥N pages → running header
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from anydoc2md.format_converters.base import (
    IMAGES_DIRNAME,
    INDEX_FILENAME,
    ConversionResult,
    load_overrides,
    resolve_source_reference,
)


# ---------------------------------------------------------------------------
# Internal block models
# ---------------------------------------------------------------------------

@dataclass
class _ImageBlock:
    page: int
    bbox: tuple[float, float, float, float]
    filename: str        # relative path: "images/img_p001_xxxx.png"
    width: int
    height: int
    page_width: float
    column: int
    y_mid: float = field(init=False)

    def __post_init__(self) -> None:
        self.y_mid = (self.bbox[1] + self.bbox[3]) / 2

    def width_em(self, max_em: float = 38.0) -> float:
        if self.page_width <= 0:
            return max_em
        ratio = (self.bbox[2] - self.bbox[0]) / self.page_width
        return round(min(ratio * max_em, max_em), 1)


@dataclass
class _TextBlock:
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    block_kind: str      # "heading" | "paragraph" | "list" | "numbered_list" | "table"
    avg_font_size: float
    column: int
    y_mid: float = field(init=False)

    def __post_init__(self) -> None:
        self.y_mid = (self.bbox[1] + self.bbox[3]) / 2


# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"[ \t]+")
_LIST_MARKER_RE = re.compile(r"^(?:[-•*+]\s+|\d+[.)]\s+)")
_NUMBERED_ITEM_RE = re.compile(r"^(\d+)[.)]\s*(.*)")
_CAPTION_RE = re.compile(
    r"^(Figure|Fig\.|Table)\s+\d+(\.\d+)*\.(?=\s|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _clean_line(line: str) -> str:
    return _WHITESPACE_RE.sub(" ", line).strip()


def _is_list_line(text: str) -> bool:
    return _LIST_MARKER_RE.match(text.strip()) is not None


def _is_caption(text: str) -> bool:
    return bool(_CAPTION_RE.match(text.strip()))


def _block_column(bbox: tuple, page_width: float, ratio: float) -> int:
    return 1 if bbox[0] > page_width * ratio else 0


def _sort_key(block: _TextBlock | _ImageBlock) -> tuple[int, int, float]:
    return (block.page, block.column, block.y_mid)


def _page_avg_font(page_dict: dict) -> float:
    sizes: list[float] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size"):
                    sizes.append(span["size"])
    return sum(sizes) / len(sizes) if sizes else 12.0


def _detect_block_kind(text: str, avg_size: float, page_avg: float) -> str:
    stripped = text.strip()
    lines = [l for l in stripped.splitlines() if l.strip()]
    if not lines:
        return "paragraph"
    if all(_is_list_line(l) for l in lines):
        return "list"
    if "|" in stripped and stripped.count("|") >= 2:
        return "table"
    if avg_size > page_avg * 1.15 and len(stripped) < 120:
        return "heading"
    bare_numbers = sum(1 for l in lines if re.match(r"^\d+[.)]$", l.strip()))
    if bare_numbers >= 2:
        return "numbered_list"
    return "paragraph"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract(
    pdf_path: Path,
    images_dir: Path,
    *,
    column_split_ratio: float,
    min_text_len: int,
) -> tuple[list[_TextBlock], list[_ImageBlock]]:
    images_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))

    text_blocks: list[_TextBlock] = []
    image_blocks: list[_ImageBlock] = []
    seen_hashes: set[str] = set()

    for page_num, page in enumerate(doc, start=1):
        page_dict = page.get_text("dict")
        page_avg = _page_avg_font(page_dict)
        pw = page.rect.width

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines_text: list[str] = []
            sizes: list[float] = []
            for line in block.get("lines", []):
                parts: list[str] = []
                for span in line.get("spans", []):
                    t = _clean_line(span.get("text", ""))
                    if t:
                        parts.append(t)
                        if span.get("size"):
                            sizes.append(span["size"])
                if parts:
                    lines_text.append(" ".join(parts))

            raw = "\n".join(lines_text).strip()
            if not raw or len(raw) < min_text_len:
                continue

            avg_size = sum(sizes) / len(sizes) if sizes else page_avg
            bbox = tuple(block["bbox"])
            text_blocks.append(_TextBlock(
                page=page_num,
                bbox=bbox,
                text=raw,
                block_kind=_detect_block_kind(raw, avg_size, page_avg),
                avg_font_size=avg_size,
                column=_block_column(bbox, pw, column_split_ratio),
            ))

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
            image_blocks.append(_ImageBlock(
                page=page_num,
                bbox=bbox,
                filename=f"{IMAGES_DIRNAME}/{filename}",
                width=base_image.get("width", 0),
                height=base_image.get("height", 0),
                page_width=pw,
                column=_block_column(bbox, pw, column_split_ratio),
            ))

    doc.close()
    return text_blocks, image_blocks


def _image_bbox(page: fitz.Page, xref: int) -> tuple[float, float, float, float]:
    for item in page.get_image_rects(xref):
        r = item
        return (r.x0, r.y0, r.x1, r.y1)
    return (0.0, 0.0, page.rect.width, 0.0)


# ---------------------------------------------------------------------------
# Assembly helpers
# ---------------------------------------------------------------------------

def _filter_running_headers(
    text_blocks: list[_TextBlock],
    min_pages: int,
) -> list[_TextBlock]:
    heading_pages: dict[str, set[int]] = {}
    for b in text_blocks:
        if b.block_kind == "heading":
            key = " ".join(b.text.split()).lower()
            heading_pages.setdefault(key, set()).add(b.page)
    running = {k for k, pages in heading_pages.items() if len(pages) >= min_pages}
    if not running:
        return text_blocks
    return [
        b for b in text_blocks
        if not (b.block_kind == "heading" and " ".join(b.text.split()).lower() in running)
    ]


def _attach_captions(
    all_blocks: list[_TextBlock | _ImageBlock],
) -> list[_TextBlock | _ImageBlock]:
    captions = [b for b in all_blocks if isinstance(b, _TextBlock) and _is_caption(b.text)]
    non_captions = [b for b in all_blocks if not (isinstance(b, _TextBlock) and _is_caption(b.text))]

    if not captions:
        return all_blocks

    images = [b for b in non_captions if isinstance(b, _ImageBlock)]
    caption_to_image: dict[int, _ImageBlock | None] = {}
    for cap in captions:
        same_page = [img for img in images if img.page == cap.page]
        if same_page:
            preceding = [img for img in same_page if img.y_mid <= cap.y_mid]
            nearest = (
                max(preceding, key=lambda img: img.y_mid)
                if preceding
                else min(same_page, key=lambda img: abs(img.y_mid - cap.y_mid))
            )
            caption_to_image[id(cap)] = nearest
        else:
            caption_to_image[id(cap)] = None

    result: list[_TextBlock | _ImageBlock] = []
    used: set[int] = set()
    for block in non_captions:
        result.append(block)
        if isinstance(block, _ImageBlock):
            attached = sorted(
                [c for c in captions if id(c) not in used and caption_to_image.get(id(c)) is block],
                key=lambda c: c.y_mid,
            )
            for cap in attached:
                result.append(cap)
                used.add(id(cap))

    for cap in captions:
        if id(cap) not in used:
            result.append(cap)

    return result


def _build_heading_map(text_blocks: list[_TextBlock]) -> dict[float, str]:
    sizes: list[float] = []
    for b in text_blocks:
        if b.block_kind == "heading":
            bucket = round(b.avg_font_size * 2) / 2
            if not any(abs(bucket - s) < 0.5 for s in sizes):
                sizes.append(bucket)
    sizes.sort(reverse=True)
    levels = ["#", "##", "###"]
    return {s: levels[min(i, 2)] for i, s in enumerate(sizes)}


def _fmt_numbered_list(text: str) -> str:
    lines = text.strip().splitlines()
    items: list[tuple[str, list[str]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = _NUMBERED_ITEM_RE.match(stripped)
        if m:
            num, inline = m.group(1), m.group(2).strip()
            items.append((num, [inline] if inline else []))
        elif items:
            items[-1][1].append(stripped)
    if not items:
        return text.strip() + "\n"
    return "\n".join(f"{n}. {' '.join(parts)}" for n, parts in items) + "\n"


def _fmt_list(text: str) -> str:
    raw = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(raw) == 1:
        parts = re.split(r"(?<!\A)[•\-\*](?=\s)", raw[0])
        if len(parts) > 1:
            raw = [p.strip() for p in parts if p.strip()]
    items = [_LIST_MARKER_RE.sub("", l).strip() for l in raw if l.strip()]
    return "\n".join(f"- {item}" for item in items) + "\n"


def _fmt_block(block: _TextBlock, heading_map: dict[float, str]) -> str:
    if block.block_kind == "heading":
        single = " ".join(block.text.split())
        bucket = round(block.avg_font_size * 2) / 2
        closest = min(heading_map.keys(), key=lambda s: abs(s - bucket), default=None)
        prefix = heading_map.get(closest, "##") if closest is not None else "##"
        return f"{prefix} {single}\n"
    if block.block_kind == "numbered_list":
        return _fmt_numbered_list(block.text)
    if block.block_kind == "list":
        return _fmt_list(block.text)
    if block.block_kind == "table":
        return f"```\n{block.text.strip()}\n```\n"
    if _is_caption(block.text):
        return f"*{' '.join(block.text.split())}*\n"
    return " ".join(block.text.split()) + "\n"


def _fmt_image(block: _ImageBlock) -> str:
    alt = f"Figure (page {block.page})"
    w = block.width_em()
    return (
        f'<img src="{block.filename}" alt="{alt}"'
        f' style="width: {w}em; max-width: 100%; display: block; margin: 0.5em 0;" />\n'
    )


def _assemble(
    title: str,
    source_url: str,
    text_blocks: list[_TextBlock],
    image_blocks: list[_ImageBlock],
    running_header_min_pages: int,
) -> str:
    text_blocks = _filter_running_headers(text_blocks, running_header_min_pages)
    heading_map = _build_heading_map(text_blocks)

    all_blocks: list[_TextBlock | _ImageBlock] = list(text_blocks) + list(image_blocks)
    all_blocks.sort(key=_sort_key)
    all_blocks = _attach_captions(all_blocks)

    lines: list[str] = [f"# {title}\n", f"**Source:** {source_url}\n", ""]
    current_page: int | None = None

    for block in all_blocks:
        if block.page != current_page:
            if current_page is not None:
                lines += ["", "---", ""]
            current_page = block.page
        if isinstance(block, _ImageBlock):
            lines.append(_fmt_image(block))
        else:
            lines.append(_fmt_block(block, heading_map))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf"}


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def convert(
    source_path: Path,
    staging_dir: Path,
    *,
    title: str = "",
    source_url: str = "",
    overrides: dict[str, Any] | None = None,
) -> ConversionResult:
    """
    Convert a PDF to index.md + images/ in staging_dir.
    Reads document.override.yaml from staging_dir automatically.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_overrides(staging_dir, overrides)

    column_split_ratio: float = float(cfg.get("column_split_ratio", 0.55))
    min_text_len: int = int(cfg.get("min_text_len", 10))
    running_header_min_pages: int = int(cfg.get("running_header_min_pages", 3))

    resolved_title = title or source_path.stem.replace("_", " ")
    resolved_url = resolve_source_reference(source_path, source_url)

    images_dir = staging_dir / "images"
    text_blocks, image_blocks = _extract(
        source_path,
        images_dir,
        column_split_ratio=column_split_ratio,
        min_text_len=min_text_len,
    )

    md = _assemble(
        resolved_title,
        resolved_url,
        text_blocks,
        image_blocks,
        running_header_min_pages,
    )

    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=len(image_blocks),
    )
