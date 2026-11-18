"""Conservative repeated-margin furniture detection, independent of font class."""
from __future__ import annotations

import re
from collections import defaultdict

from anydoc2md.format_converters._pdf_blocks import TextBlock


def _signature(block: TextBlock) -> tuple[str, str] | None:
    if block.page_height <= 0:
        return ("heading", " ".join(block.text.split())) if block.block_kind == "heading" else None
    edge = "top" if block.bbox[3] < block.page_height * 0.10 else (
        "bottom" if block.bbox[1] > block.page_height * 0.90 else ""
    )
    side = ""
    if not edge and block.page_width > 0:
        side = "left" if block.bbox[2] < block.page_width * 0.10 else (
            "right" if block.bbox[0] > block.page_width * 0.90 else ""
        )
        edge = side
    text = " ".join(block.text.split())
    if not edge or not text or len(text) > 240:
        return None
    # Group by edge and stable vertical band, not merely repeated wording.
    band = edge if side else f"{edge}:{round(block.y_mid / block.page_height / 0.02)}"
    match = re.fullmatch(r"Page\s+(\d+)\s+of\s+(\d+)", text, re.IGNORECASE)
    if match:
        number, total = map(int, match.groups())
        if 1 <= number <= total:
            return band, f"page-number-offset:{number - block.page}:total:{total}"
        return None
    if re.fullmatch(r"\d+", text):
        return band, f"page-number-offset:{int(text) - block.page}"
    # Only separator-delimited leading/trailing page numbers vary. Never fold
    # embedded digits (Step 1 / Step 2) or units via Roman-numeral substitutions.
    numbered = re.fullmatch(r"(\d+)\s*[-\u2013\u2014|]\s*(.+)", text)
    trailing = re.fullmatch(r"(.+?)\s*[-\u2013\u2014|]\s*(\d+)", text)
    if numbered:
        number, label = numbered.groups()
        return band, f"prefix:{label}:offset:{int(number) - block.page}"
    if trailing:
        label, number = trailing.groups()
        return band, f"suffix:{label}:offset:{int(number) - block.page}"
    return band, f"exact:{text}"


def filter_page_furniture(blocks: list[TextBlock], min_pages: int) -> list[TextBlock]:
    pages: dict[tuple[str, str], set[int]] = {}
    by_text: dict[str, list[TextBlock]] = defaultdict(list)
    for block in blocks:
        by_text[" ".join(block.text.split())].append(block)
        signature = _signature(block)
        if signature:
            pages.setdefault(signature, set()).add(block.page)
    repeated = {key for key, seen in pages.items() if len(seen) >= max(3, min_pages)}
    protected: set[int] = set()
    for edge, label in repeated:
        if not label.startswith("exact:"):
            continue
        matches = by_text[label.removeprefix("exact:")]
        # Compare against the whole document: the genuine title can sit outside
        # the margin band occupied by its running copies.
        canonical = min(matches, key=lambda b: (-b.avg_font_size, b.page, b.bbox[1]))
        running = [b for b in matches if _signature(b) == (edge, label)]
        # Classification alone is not evidence of a real title: all running
        # copies can be classified as headings. Require location or typography
        # independent of the repeated group.
        outside = _signature(canonical) != (edge, label)
        larger = canonical.avg_font_size > min(b.avg_font_size for b in running) + 0.5
        if (outside and canonical.block_kind == "heading") or larger:
            protected.add(id(canonical))
    return [block for block in blocks if id(block) in protected or _signature(block) not in repeated]


def removed_block_audit(blocks: list[TextBlock], min_pages: int) -> list[dict]:
    retained = {id(block) for block in filter_page_furniture(blocks, min_pages)}
    return [
        {"page": block.page, "bbox": list(block.bbox), "text": block.text,
         "signature": _signature(block), "reason": "repeated edge furniture"}
        for block in blocks if id(block) not in retained
    ]
