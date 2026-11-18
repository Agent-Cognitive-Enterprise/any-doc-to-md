"""Conservative numbered-title families and narrative figure-reference handling."""
from __future__ import annotations

from collections import defaultdict
import re

from ._pdf_blocks import TextBlock, sort_key

NUMBERED_TITLE = re.compile(r"^([^\W\d_][\w -]{0,30}?)\s+(\d+)\s*:\s+\S", re.UNICODE)
FIGURE_REFERENCE = re.compile(r"^(?:figures?|fig\.|tables?)\s+\d", re.IGNORECASE)


def major_numbered_titles(blocks: list[TextBlock]) -> set[int]:
    """Peer numbered title families outrank their smaller objective/subheadings.

    Global font ranking alone collapses headings when covers and large diagram
    labels consume every rank. Require multiple numbered titles and a larger
    font than typical subheadings; do not let added peer headings raise their own
    detection threshold or promote arbitrary body prose.
    """
    headings = [b for b in blocks if b.block_kind == "heading"]
    if not headings:
        return set()
    sizes = sorted(round(b.avg_font_size * 2) / 2 for b in headings)
    typical = sizes[(len(sizes) - 1) // 4]
    families: dict[str, list[tuple[str, TextBlock]]] = defaultdict(list)
    for block in blocks:
        text = " ".join(block.text.split())
        match = NUMBERED_TITLE.match(text)
        if match and not FIGURE_REFERENCE.match(text) and block.avg_font_size > typical * 1.2:
            families[match[1].casefold()].append((match[2], block))
    titles = [block for rows in families.values() if len({number for number, _ in rows}) >= 2
              for _, block in rows]
    if not titles:
        return set()
    promoted = {id(block) for block in titles}
    # Once a family is active, equally prominent non-family headings are peers,
    # not children of its final member. Keep subsequent Skills/Glossary peers too.
    active_size = None
    for block in sorted(blocks, key=sort_key):
        if id(block) in promoted:
            active_size = block.avg_font_size
        elif (active_size is not None and block.block_kind == "heading"
              and abs(block.avg_font_size - active_size) <= 0.25
              and not _is_diagram_label(block)):
            promoted.add(id(block))
    return promoted


def _bucket(block: TextBlock) -> float:
    return round(block.avg_font_size * 2) / 2


def _is_diagram_label(block: TextBlock) -> bool:
    """Single letters, letter-plus-caption labels and figure references are not sections."""
    return (len(block.text.strip()) <= 1
            or re.match(r"^\s*[^\W\d_]\s*\n", block.text) is not None
            or FIGURE_REFERENCE.match(" ".join(block.text.split())) is not None)


def _parent_tier_level(
    blocks: list[TextBlock], promoted: set[int], size: float, heading_map: dict[float, str],
) -> int | None:
    """Deepest larger heading tier that partitions this numbered family, if any.

    A real intermediate parent (Part > Chapter > Exercise N:) recurs, and at
    least two of its occurrences each introduce their own family members. Cover
    titles appear once and diagram letters are excluded, so neither qualifies;
    that keeps workbook modules as top sections despite larger page labels.
    """
    groups: dict[float, list[int]] = defaultdict(list)
    for block in sorted(blocks, key=sort_key):
        bucket = _bucket(block)
        if id(block) in promoted and bucket == size and NUMBERED_TITLE.match(" ".join(block.text.split())):
            for counts in groups.values():
                if counts:
                    counts[-1] += 1
        elif (block.block_kind == "heading" and id(block) not in promoted
              and bucket > size + 0.25 and not _is_diagram_label(block)):
            groups[bucket].append(0)
    levels = [len(heading_map[bucket]) for bucket, counts in groups.items()
              if bucket in heading_map and sum(1 for count in counts if count) >= 2]
    return max(levels) if levels else None


def align_promoted_heading_levels(
    blocks: list[TextBlock], promoted: set[int], heading_map: dict[float, str],
) -> dict[float, str]:
    """Keep larger parents intact and reserve child levels below each family.

    Promotion changes the typography map too: a smaller subsection must never
    collide with its promoted parent. Preserve already shallower family levels,
    and nest a family below any recurring larger tier that partitions it.
    """
    result = dict(heading_map)
    for size in sorted({_bucket(b) for b in blocks if id(b) in promoted}, reverse=True):
        parent = _parent_tier_level(blocks, promoted, size, heading_map)
        level = parent + 1 if parent is not None else min(len(result.get(size, "##")), 2)
        result[size] = "#" * level
        for smaller in result:
            if smaller < size:
                result[smaller] = "#" * max(len(result[smaller]), level + 1)
    return result
