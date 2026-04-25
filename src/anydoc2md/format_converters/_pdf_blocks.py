"""Shared PDF block models and text classification helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

WHITESPACE_RE = re.compile(r"[ \t]+")
LIST_MARKER_RE = re.compile(r"^(?:[-•*+]\s+|\d+[.)]\s+)")
NUMBERED_ITEM_RE = re.compile(r"^(\d+)[.)]\s*(.*)")
CAPTION_RE = re.compile(
    r"^(Figure|Fig\.|Table)\s+\d+(\.\d+)*\.(?=\s|$)",
    re.IGNORECASE,
)


@dataclass
class ImageBlock:
    page: int
    bbox: tuple[float, float, float, float]
    filename: str
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
class TextBlock:
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    block_kind: str
    avg_font_size: float
    column: int
    y_mid: float = field(init=False)

    def __post_init__(self) -> None:
        self.y_mid = (self.bbox[1] + self.bbox[3]) / 2


def clean_line(line: str) -> str:
    return WHITESPACE_RE.sub(" ", line).strip()


def is_list_line(text: str) -> bool:
    return LIST_MARKER_RE.match(text.strip()) is not None


def is_caption(text: str) -> bool:
    return bool(CAPTION_RE.match(text.strip()))


def block_column(bbox: tuple, page_width: float, ratio: float) -> int:
    return 1 if bbox[0] > page_width * ratio else 0


def sort_key(block: TextBlock | ImageBlock) -> tuple[int, int, float]:
    return (block.page, block.column, block.y_mid)


def page_avg_font(page_dict: dict) -> float:
    sizes: list[float] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size"):
                    sizes.append(span["size"])
    return sum(sizes) / len(sizes) if sizes else 12.0


def detect_block_kind(text: str, avg_size: float, page_avg: float) -> str:
    stripped = text.strip()
    lines = [line for line in stripped.splitlines() if line.strip()]
    if not lines:
        return "paragraph"
    if all(is_list_line(line) for line in lines):
        return "list"
    if "|" in stripped and stripped.count("|") >= 2:
        return "table"
    if avg_size > page_avg * 1.15 and len(stripped) < 120:
        return "heading"
    bare_numbers = sum(1 for line in lines if re.match(r"^\d+[.)]$", line.strip()))
    if bare_numbers >= 2:
        return "numbered_list"
    return "paragraph"
