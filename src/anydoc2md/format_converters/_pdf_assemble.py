"""Markdown assembly helpers for the in-house PDF converter."""

from __future__ import annotations

import re

from anydoc2md.format_converters._pdf_blocks import (
    LIST_MARKER_RE,
    NUMBERED_ITEM_RE,
    ImageBlock,
    TextBlock,
    is_caption,
    sort_key,
)


def assemble_markdown(
    title: str,
    source_url: str,
    text_blocks: list[TextBlock],
    image_blocks: list[ImageBlock],
    running_header_min_pages: int,
) -> str:
    text_blocks = _filter_running_headers(text_blocks, running_header_min_pages)
    heading_map = _build_heading_map(text_blocks)

    all_blocks: list[TextBlock | ImageBlock] = list(text_blocks) + list(image_blocks)
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
    all_blocks: list[TextBlock | ImageBlock],
) -> list[TextBlock | ImageBlock]:
    captions = [b for b in all_blocks if isinstance(b, TextBlock) and is_caption(b.text)]
    non_captions = [b for b in all_blocks if not (isinstance(b, TextBlock) and is_caption(b.text))]

    if not captions:
        return all_blocks

    images = [b for b in non_captions if isinstance(b, ImageBlock)]
    caption_to_image: dict[int, ImageBlock | None] = {}
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

    result: list[TextBlock | ImageBlock] = []
    used: set[int] = set()
    for block in non_captions:
        result.append(block)
        if isinstance(block, ImageBlock):
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
