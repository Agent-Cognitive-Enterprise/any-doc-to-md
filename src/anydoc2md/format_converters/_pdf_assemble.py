"""Markdown assembly helpers for the in-house PDF converter."""

from __future__ import annotations

import re

from anydoc2md.format_converters._pdf_blocks import (
    LIST_MARKER_RE,
    NUMBERED_ITEM_RE,
    ImageBlock,
    TableBlock,
    TextBlock,
    is_caption,
    sort_key,
)

TABLE_TEXT_SUPPRESSION_OVERLAP = 0.65


def assemble_markdown(
    title: str,
    source_url: str,
    text_blocks: list[TextBlock],
    image_blocks: list[ImageBlock],
    running_header_min_pages: int,
    table_blocks: list[TableBlock] | None = None,
) -> str:
    table_blocks = list(table_blocks or [])
    if table_blocks:
        text_blocks = _suppress_table_text_blocks(text_blocks, table_blocks)
    text_blocks = _filter_running_headers(text_blocks, running_header_min_pages)
    heading_map = _build_heading_map(text_blocks)

    all_blocks: list[TextBlock | ImageBlock | TableBlock] = (
        list(text_blocks) + list(image_blocks) + table_blocks
    )
    all_blocks.sort(key=sort_key)
    all_blocks = _attach_captions(all_blocks)

    lines: list[str] = [f"# {title}\n", f"**Source:** {source_url}\n", ""]
    current_page: int | None = None

    for block in all_blocks:
        if block.page != current_page:
            if current_page is not None:
                lines += ["", "---", ""]
            current_page = block.page
        if isinstance(block, ImageBlock):
            lines.append(_fmt_image(block))
        elif isinstance(block, TableBlock):
            lines.append(_fmt_table(block))
        else:
            lines.append(_fmt_block(block, heading_map))

    return "\n".join(lines)


def _filter_running_headers(
    text_blocks: list[TextBlock],
    min_pages: int,
) -> list[TextBlock]:
    heading_pages: dict[str, set[int]] = {}
    for block in text_blocks:
        if block.block_kind == "heading":
            key = " ".join(block.text.split()).lower()
            heading_pages.setdefault(key, set()).add(block.page)
    running = {key for key, pages in heading_pages.items() if len(pages) >= min_pages}
    if not running:
        return text_blocks
    return [
        block for block in text_blocks
        if not (
            block.block_kind == "heading"
            and " ".join(block.text.split()).lower() in running
        )
    ]


def _attach_captions(
    all_blocks: list[TextBlock | ImageBlock | TableBlock],
) -> list[TextBlock | ImageBlock | TableBlock]:
    captions = [b for b in all_blocks if isinstance(b, TextBlock) and is_caption(b.text)]
    if not captions:
        return all_blocks

    images = [b for b in all_blocks if isinstance(b, ImageBlock)]
    tables = [b for b in all_blocks if isinstance(b, TableBlock)]
    caption_to_target: dict[int, ImageBlock | TableBlock | None] = {}
    for cap in captions:
        if _is_table_caption(cap):
            same_page_tables = [table for table in tables if table.page == cap.page]
            caption_to_target[id(cap)] = (
                min(same_page_tables, key=lambda table: abs(table.y_mid - cap.y_mid))
                if same_page_tables
                else None
            )
        else:
            same_page_images = [img for img in images if img.page == cap.page]
            if same_page_images:
                preceding = [img for img in same_page_images if img.y_mid <= cap.y_mid]
                caption_to_target[id(cap)] = (
                    max(preceding, key=lambda img: img.y_mid)
                    if preceding
                    else min(same_page_images, key=lambda img: abs(img.y_mid - cap.y_mid))
                )
            else:
                caption_to_target[id(cap)] = None

    # Only relocate a caption to hug its target when the two are already adjacent
    # in reading order. Otherwise, pulling the caption out would leapfrog the
    # intervening body text, so leave such captions in their natural position.
    order_index = {id(block): i for i, block in enumerate(all_blocks)}
    for cap in captions:
        target = caption_to_target.get(id(cap))
        if target is not None and not _caption_adjacent_to_target(
            cap, target, all_blocks, order_index
        ):
            caption_to_target[id(cap)] = None

    non_captions = [
        b for b in all_blocks
        if not (
            isinstance(b, TextBlock)
            and is_caption(b.text)
            and caption_to_target.get(id(b)) is not None
        )
    ]

    result: list[TextBlock | ImageBlock | TableBlock] = []
    used: set[int] = set()
    for block in non_captions:
        before = sorted(
            [
                c for c in captions
                if (
                    id(c) not in used
                    and caption_to_target.get(id(c)) is block
                    and _caption_goes_before_target(c, block)
                )
            ],
            key=lambda c: c.y_mid,
        )
        for cap in before:
            result.append(cap)
            used.add(id(cap))

        result.append(block)
        if isinstance(block, TextBlock) and is_caption(block.text):
            used.add(id(block))

        after = sorted(
            [
                c for c in captions
                if (
                    id(c) not in used
                    and caption_to_target.get(id(c)) is block
                    and not _caption_goes_before_target(c, block)
                )
            ],
            key=lambda c: c.y_mid,
        )
        for cap in after:
            result.append(cap)
            used.add(id(cap))

    for cap in captions:
        if id(cap) not in used:
            result.append(cap)

    return result


def _is_table_caption(block: TextBlock) -> bool:
    return block.text.lstrip().lower().startswith("table ")


def _caption_goes_before_target(
    caption: TextBlock,
    target: ImageBlock | TableBlock,
) -> bool:
    return isinstance(target, TableBlock) and caption.y_mid <= target.y_mid


def _caption_adjacent_to_target(
    caption: TextBlock,
    target: ImageBlock | TableBlock,
    ordered_blocks: list[TextBlock | ImageBlock | TableBlock],
    order_index: dict[int, int],
) -> bool:
    lo, hi = sorted((order_index[id(caption)], order_index[id(target)]))
    return all(
        isinstance(block, TextBlock) and is_caption(block.text)
        for block in ordered_blocks[lo + 1 : hi]
    )


def _suppress_table_text_blocks(
    text_blocks: list[TextBlock],
    table_blocks: list[TableBlock],
) -> list[TextBlock]:
    return [
        block for block in text_blocks
        if not _is_text_inside_table(block, table_blocks)
    ]


def _is_text_inside_table(
    text_block: TextBlock,
    table_blocks: list[TableBlock],
) -> bool:
    if is_caption(text_block.text):
        return False
    return any(
        _center_inside(text_block.bbox, table.bbox)
        and _overlap_ratio_against_text(text_block.bbox, table.bbox)
        >= TABLE_TEXT_SUPPRESSION_OVERLAP
        for table in table_blocks
        if table.page == text_block.page
    )


def _center_inside(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    x_mid = (inner[0] + inner[2]) / 2
    y_mid = (inner[1] + inner[3]) / 2
    return outer[0] <= x_mid <= outer[2] and outer[1] <= y_mid <= outer[3]


def _overlap_ratio_against_text(
    text_bbox: tuple[float, float, float, float],
    table_bbox: tuple[float, float, float, float],
) -> float:
    text_area = _rect_area(text_bbox)
    if text_area <= 0:
        return 0.0
    return _overlap_area(text_bbox, table_bbox) / text_area


def _rect_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _overlap_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return _rect_area((x0, y0, x1, y1))


def _build_heading_map(text_blocks: list[TextBlock]) -> dict[float, str]:
    sizes: list[float] = []
    for block in text_blocks:
        if block.block_kind == "heading":
            bucket = round(block.avg_font_size * 2) / 2
            if not any(abs(bucket - size) < 0.5 for size in sizes):
                sizes.append(bucket)
    sizes.sort(reverse=True)
    levels = ["#", "##", "###"]
    return {size: levels[min(index, 2)] for index, size in enumerate(sizes)}


def _fmt_numbered_list(text: str) -> str:
    lines = text.strip().splitlines()
    items: list[tuple[str, list[str]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = NUMBERED_ITEM_RE.match(stripped)
        if match:
            num, inline = match.group(1), match.group(2).strip()
            items.append((num, [inline] if inline else []))
        elif items:
            items[-1][1].append(stripped)
    if not items:
        return text.strip() + "\n"
    return "\n".join(f"{num}. {' '.join(parts)}" for num, parts in items) + "\n"


def _fmt_list(text: str) -> str:
    raw = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(raw) == 1:
        parts = re.split(r"(?<!\A)[•\-\*](?=\s)", raw[0])
        if len(parts) > 1:
            raw = [part.strip() for part in parts if part.strip()]
    items = [LIST_MARKER_RE.sub("", line).strip() for line in raw if line.strip()]
    return "\n".join(f"- {item}" for item in items) + "\n"


def _fmt_block(block: TextBlock, heading_map: dict[float, str]) -> str:
    if block.block_kind == "heading":
        single = " ".join(block.text.split())
        bucket = round(block.avg_font_size * 2) / 2
        closest = min(heading_map.keys(), key=lambda size: abs(size - bucket), default=None)
        prefix = heading_map.get(closest, "##") if closest is not None else "##"
        return f"{prefix} {single}\n"
    if block.block_kind == "numbered_list":
        return _fmt_numbered_list(block.text)
    if block.block_kind == "list":
        return _fmt_list(block.text)
    if block.block_kind == "table":
        return f"```\n{block.text.strip()}\n```\n"
    if is_caption(block.text):
        return f"*{' '.join(block.text.split())}*\n"
    return " ".join(block.text.split()) + "\n"


def _fmt_image(block: ImageBlock) -> str:
    alt = f"Figure (page {block.page})"
    width = block.width_em()
    return (
        f'<img src="{block.filename}" alt="{alt}"'
        f' style="width: {width}em; max-width: 100%; display: block; margin: 0.5em 0;" />\n'
    )


def _fmt_table(block: TableBlock) -> str:
    return block.markdown.strip() + "\n"
