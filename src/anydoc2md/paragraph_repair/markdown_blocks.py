"""Conservative Markdown block splitting for paragraph repair.

This is not a full CommonMark parser. Lazy continuation lines for lists,
blockquotes, and HTML are deliberately classified conservatively rather than
interpreted with full Markdown context. Setext headings are recognised only
as a single content line followed by a `=`/`-` underline; multi-line setext
titles fall back to a separate prose block plus a single-line heading, which
is still safe because headings remain hard boundaries.
"""
from __future__ import annotations

import re

from anydoc2md.paragraph_repair.model import BlockKind, MarkdownBlock

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_LIST_ITEM_RE = re.compile(
    r"^\s{0,3}(?:[-+*]\s+|[-+*]\s+\[[ xX]\]\s+|•\s+|\d+[.)]\s+)"
)
_PIPE_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_HTML_START_RE = re.compile(
    r"^\s{0,3}(?:<!--|<!doctype\b|</?(?:article|aside|div|figure|figcaption|"
    r"footer|header|main|nav|section|table|tbody|td|tfoot|th|thead|tr)\b)",
    re.IGNORECASE,
)
_HTML_IMAGE_RE = re.compile(r"^\s{0,3}<img\b", re.IGNORECASE)
_CAPTION_RE = re.compile(
    r"^\s{0,3}[*_]*(?:figure|fig\.|table)\s+\d+(?:\.\d+)*[\).:]\s+\S",
    re.IGNORECASE,
)
_HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_SETEXT_UNDERLINE_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")


def split_markdown_blocks(md_text: str) -> list[MarkdownBlock]:
    """Split Markdown into conservative blocks without normalizing text."""
    lines = md_text.splitlines(keepends=True)
    blocks: list[MarkdownBlock] = []
    index = 0

    if _has_front_matter(lines):
        end_index = _front_matter_end_index(lines)
        blocks.append(_make_block("front_matter", lines, 0, end_index))
        index = end_index + 1

    while index < len(lines):
        line = lines[index]
        if _is_blank(line):
            next_index = _consume_while(lines, index, _is_blank)
            blocks.append(_make_block("blank", lines, index, next_index - 1))
            index = next_index
            continue

        fence = _fence_marker(line)
        if fence is not None:
            next_index = _consume_code_fence(lines, index, fence)
            blocks.append(_make_block("code_fence", lines, index, next_index - 1))
            index = next_index
            continue

        if _is_setext_heading_start(lines, index):
            blocks.append(_make_block("heading", lines, index, index + 1))
            index += 2
            continue

        if _is_whitespace_table_start(lines, index):
            next_index = _consume_whitespace_table(lines, index)
            blocks.append(_make_block("table", lines, index, next_index - 1))
            index = next_index
            continue

        if _is_pipe_table_start(lines, index):
            next_index = _consume_pipe_table(lines, index)
            blocks.append(_make_block("table", lines, index, next_index - 1))
            index = next_index
            continue

        kind = classify_line(line)
        if kind == "html":
            next_index = _consume_html_block(lines, index)
            blocks.append(_make_block(kind, lines, index, next_index - 1))
            index = next_index
            continue

        if kind in {"table", "list_item", "blockquote", "indented_code"}:
            next_index = _consume_same_kind(lines, index, kind)
            blocks.append(_make_block(kind, lines, index, next_index - 1))
            index = next_index
            continue

        if kind != "prose":
            blocks.append(_make_block(kind, lines, index, index))
            index += 1
            continue

        next_index = _consume_prose(lines, index)
        blocks.append(_make_block("prose", lines, index, next_index - 1))
        index = next_index

    return blocks


def reconstruct_markdown(blocks: list[MarkdownBlock]) -> str:
    """Rebuild Markdown from block text."""
    return "".join(block.text for block in blocks)


def classify_line(line: str) -> BlockKind:
    """Classify one Markdown line outside fenced code/front matter context."""
    if _is_blank(line):
        return "blank"
    if _fence_marker(line) is not None:
        return "code_fence"
    if is_heading(line):
        return "heading"
    if is_list_item(line):
        return "list_item"
    if is_image_line(line):
        return "image"
    if is_caption_line(line):
        return "caption"
    if is_table_like(line):
        return "table"
    if is_horizontal_rule(line):
        return "horizontal_rule"
    if line.startswith(("    ", "\t")):
        return "indented_code"
    if line.lstrip().startswith(">"):
        return "blockquote"
    if is_html_block_start(line):
        return "html"
    return "prose"


def is_heading(line: str) -> bool:
    return bool(_HEADING_RE.match(_strip_newline(line)))


def is_list_item(line: str) -> bool:
    return bool(_LIST_ITEM_RE.match(_strip_newline(line)))


def is_table_like(line: str) -> bool:
    text = _strip_newline(line).strip()
    if not text:
        return False
    if _PIPE_TABLE_SEPARATOR_RE.match(text):
        return True
    if _is_pipe_table_row(text):
        return True
    return _is_whitespace_table_data_row(text)


def is_image_line(line: str) -> bool:
    text = _strip_newline(line).strip()
    return text.startswith("![") or bool(_HTML_IMAGE_RE.match(text))


def is_caption_line(line: str) -> bool:
    return bool(_CAPTION_RE.match(_strip_newline(line).strip()))


def is_horizontal_rule(line: str) -> bool:
    return bool(_HORIZONTAL_RULE_RE.match(_strip_newline(line)))


def is_html_block_start(line: str) -> bool:
    return bool(_HTML_START_RE.match(_strip_newline(line)))


def _has_front_matter(lines: list[str]) -> bool:
    end_index = _front_matter_end_index(lines)
    return (
        bool(lines)
        and _strip_newline(lines[0]).strip() == "---"
        and end_index > 0
        and _looks_like_front_matter(lines[1:end_index])
    )


def _front_matter_end_index(lines: list[str]) -> int:
    for index, line in enumerate(lines[1:], start=1):
        stripped = _strip_newline(line).strip()
        if stripped in {"---", "..."}:
            return index
    return -1


def _consume_code_fence(lines: list[str], start_index: int, fence: str) -> int:
    marker = fence[0]
    min_len = len(fence)
    closing_re = re.compile(rf"^\s{{0,3}}{re.escape(marker)}{{{min_len},}}\s*$")
    for index in range(start_index + 1, len(lines)):
        if closing_re.match(_strip_newline(lines[index])):
            return index + 1
    return len(lines)


def _consume_whitespace_table(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        if not _is_whitespace_table_candidate(_strip_newline(lines[index]).strip()):
            break
        index += 1
    return index


def _consume_pipe_table(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        text = _strip_newline(lines[index]).strip()
        if not text or "|" not in text:
            break
        index += 1
    return index


def _consume_same_kind(lines: list[str], start_index: int, kind: BlockKind) -> int:
    index = start_index + 1
    while index < len(lines):
        if _is_blank(lines[index]):
            break
        if classify_line(lines[index]) != kind:
            break
        index += 1
    return index


def _consume_html_block(lines: list[str], start_index: int) -> int:
    closing_re = _html_closing_re(lines[start_index])
    index = start_index + 1
    while index < len(lines):
        if closing_re is not None and closing_re.match(_strip_newline(lines[index])):
            return index + 1
        if _is_blank(lines[index]):
            break
        index += 1
    return index


def _consume_prose(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        if _fence_marker(lines[index]) is not None:
            break
        if _is_setext_heading_start(lines, index):
            break
        if _is_whitespace_table_start(lines, index):
            break
        if _is_pipe_table_start(lines, index):
            break
        if classify_line(lines[index]) != "prose":
            break
        index += 1
    return index


def _consume_while(lines: list[str], start_index: int, predicate) -> int:
    index = start_index
    while index < len(lines) and predicate(lines[index]):
        index += 1
    return index


def _make_block(
    kind: BlockKind,
    lines: list[str],
    start_index: int,
    end_index: int,
) -> MarkdownBlock:
    return MarkdownBlock(
        kind=kind,
        text="".join(lines[start_index:end_index + 1]),
        start_line=start_index + 1,
        end_line=end_index + 1,
    )


def _fence_marker(line: str) -> str | None:
    match = _FENCE_RE.match(_strip_newline(line))
    return match.group(1) if match else None


def _is_blank(line: str) -> bool:
    return _strip_newline(line).strip() == ""


def _is_pipe_table_row(text: str) -> bool:
    if text.count("|") < 2:
        return False
    return text.startswith("|") or text.endswith("|")


def _is_pipe_table_start(lines: list[str], start_index: int) -> bool:
    if start_index + 1 >= len(lines):
        return False
    first = _strip_newline(lines[start_index]).strip()
    second = _strip_newline(lines[start_index + 1]).strip()
    if "|" not in first:
        return False
    cells = [cell for cell in first.split("|") if cell.strip()]
    if len(cells) < 2:
        return False
    return bool(_PIPE_TABLE_SEPARATOR_RE.match(second))


def _is_setext_heading_start(lines: list[str], start_index: int) -> bool:
    if start_index + 1 >= len(lines):
        return False
    text = _strip_newline(lines[start_index]).strip()
    if not text or classify_line(lines[start_index]) != "prose":
        return False
    underline = _strip_newline(lines[start_index + 1]).strip()
    return bool(_SETEXT_UNDERLINE_RE.match(underline))


def _is_whitespace_table_start(lines: list[str], start_index: int) -> bool:
    if start_index + 1 >= len(lines):
        return False
    first = _strip_newline(lines[start_index]).strip()
    second = _strip_newline(lines[start_index + 1]).strip()
    return (
        _is_whitespace_table_candidate(first)
        and _is_whitespace_table_data_row(second)
    )


def _is_whitespace_table_data_row(text: str) -> bool:
    return _is_whitespace_table_candidate(text) and any(
        any(char.isdigit() for char in column)
        for column in _split_whitespace_columns(text)
    )


def _is_whitespace_table_candidate(text: str) -> bool:
    columns = [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]
    if len(columns) < 2:
        return False
    if len(text) > 160:
        return False
    if text.endswith((".", "?", "!")):
        return False
    return all(len(column) <= 40 for column in columns)


def _split_whitespace_columns(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]


def _looks_like_front_matter(lines: list[str]) -> bool:
    content_lines = [_strip_newline(line).strip() for line in lines if line.strip()]
    if not content_lines:
        return False
    if any(line.startswith("#") for line in content_lines):
        return False
    return any(":" in line for line in content_lines)


def _html_closing_re(line: str) -> re.Pattern[str] | None:
    match = re.match(r"^\s{0,3}<([A-Za-z][A-Za-z0-9-]*)\b", _strip_newline(line))
    if match is None:
        return None
    tag = match.group(1)
    if tag.lower() in {"img", "br", "hr", "meta", "link", "input"}:
        return None
    return re.compile(rf"^\s{{0,3}}</{re.escape(tag)}\s*>\s*$", re.IGNORECASE)


def _strip_newline(line: str) -> str:
    return line.rstrip("\r\n")
