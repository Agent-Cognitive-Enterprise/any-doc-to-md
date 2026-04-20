"""Shared helpers for parsing and resolving image references in Markdown output."""

from __future__ import annotations

import re
from pathlib import Path


_IMG_TAG_RE = re.compile(r"<img\s[^>]*>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r"""src\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)

# Matches Markdown image syntax: ![alt](dest)
# dest may include an optional title, e.g. (images/x.png "Title")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

_EXTERNAL_PREFIXES = ("http://", "https://", "data:")


def extract_image_srcs(md_text: str) -> list[str]:
    """Return image src/dest strings found in md_text (may include duplicates)."""
    srcs: list[str] = []

    for m in _IMG_TAG_RE.finditer(md_text):
        tag = m.group(0)
        src_m = _IMG_SRC_RE.search(tag)
        if src_m:
            src = src_m.group(2).strip()
            if src:
                srcs.append(src)

    for m in _MD_IMAGE_RE.finditer(md_text):
        dest = m.group(1).strip()
        src = _parse_markdown_destination(dest)
        if src:
            srcs.append(src)

    return srcs


def image_ref_key(src: str) -> str:
    """
    Return a stable key for de-duplicating image refs across HTML/Markdown syntax.

    For local paths we use the basename so `images/a.png` and `./images/a.png`
    count as one. For external URLs we keep the full (stripped) string.
    """
    cleaned = _strip_query_fragment(src).strip()
    if _is_external(cleaned) or cleaned.lower().startswith("file://"):
        return cleaned
    cleaned = cleaned.replace("\\", "/")
    return Path(cleaned).name or cleaned


def resolve_local_image_ref(staging_dir: Path, src: str) -> tuple[Path | None, str | None]:
    """
    Resolve an image reference against staging_dir safely.

    Returns:
        (path, None) when src is a safe local path and exists.
        (None, None) when src is an external URL (http/https/data) that we cannot validate locally.
        (None, reason) when src is an unsafe/unsupported local ref or a missing local file.
    """
    cleaned = _strip_query_fragment(src).strip()
    if not cleaned:
        return None, "Empty image reference."

    if _is_external(cleaned):
        return None, None

    lowered = cleaned.lower()
    if lowered.startswith("file://"):
        return None, "Absolute file:// image references are not supported."

    cleaned = cleaned.replace("\\", "/")

    # Absolute UNIX paths, UNC paths, and Windows drive paths are all unsafe in staging output.
    if cleaned.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", cleaned):
        return None, f"Absolute image reference not allowed: {src}"

    candidate = (staging_dir / cleaned).resolve()
    root = staging_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, f"Image reference escapes staging dir: {src}"

    if not candidate.exists():
        return None, f"Missing image file: {src}"

    return candidate, None


def _parse_markdown_destination(dest: str) -> str:
    """
    Extract the URL/path portion of a Markdown link destination.

    Supports:
      - `images/x.png`
      - `images/x.png "Title"`
      - `<images/x.png>`
      - `<images/x.png> "Title"`
    """
    value = dest.strip()
    if not value:
        return ""

    if value.startswith("<"):
        end = value.find(">")
        if end > 1:
            return value[1:end].strip()

    # Fall back: take the first whitespace-separated token.
    return value.split()[0].strip().strip("'\"")


def _strip_query_fragment(value: str) -> str:
    value = value.split("#", 1)[0]
    value = value.split("?", 1)[0]
    return value


def _is_external(value: str) -> bool:
    lowered = value.lstrip().lower()
    return lowered.startswith(_EXTERNAL_PREFIXES)

