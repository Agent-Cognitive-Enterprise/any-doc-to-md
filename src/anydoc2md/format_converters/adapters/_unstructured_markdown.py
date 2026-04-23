"""Render Unstructured elements into conservative Markdown."""

from __future__ import annotations

import re
from typing import Any, Iterable

_SKIP_CATEGORIES = {"Footer", "Header", "Image", "PageNumber"}


def render_elements_to_markdown(elements: Iterable[Any]) -> str:
    """Render a sequence of Unstructured elements into Markdown text."""
    parts: list[str] = []
    previous_kind = ""

    for element in elements:
        kind, block = _render_element(element)
        if not block:
            continue

        if kind == "list_item":
            if previous_kind == "list_item":
                parts.append("\n")
            elif parts:
                parts.append("\n\n")
        elif parts:
            parts.append("\n\n")

        parts.append(block)
        previous_kind = kind

    markdown = "".join(parts).strip()
    return re.sub(r"\n{3,}", "\n\n", markdown)


def _render_element(element: Any) -> tuple[str, str]:
    category = _category_name(element)
    text = _clean_text(_element_text(element))
    if category in _SKIP_CATEGORIES:
        return "", ""
    if category == "PageBreak":
        return "page_break", "---"
    if category == "Table":
        table_html = _metadata_attr(element, "text_as_html")
        if table_html:
            return "table", str(table_html).strip()
        return "table", text
    if not text:
        return "", ""
    if category == "Title":
        level = _heading_level(element)
        return "heading", f"{'#' * level} {text}"
    if category == "ListItem":
        return "list_item", f"- {_strip_list_marker(text)}"
    if category == "FigureCaption":
        return "caption", f"*{text}*"
    return "paragraph", text


def _category_name(element: Any) -> str:
    category = getattr(element, "category", "")
    if category:
        return str(category)
    return element.__class__.__name__


def _element_text(element: Any) -> str:
    text = getattr(element, "text", "")
    return "" if text is None else str(text)


def _metadata_attr(element: Any, name: str) -> Any:
    metadata = getattr(element, "metadata", None)
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get(name)
    return getattr(metadata, name, None)


def _heading_level(element: Any) -> int:
    depth = _metadata_attr(element, "category_depth")
    if isinstance(depth, int):
        return max(1, min(depth + 1, 6))
    return 1


def _strip_list_marker(text: str) -> str:
    stripped = re.sub(r"^\s*(?:[-*+•]+|\d+[.)])\s+", "", text)
    return stripped or text


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()
