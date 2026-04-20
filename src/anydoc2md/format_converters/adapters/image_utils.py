"""
Image dimension annotation utility.

After a converter runs, image files may be present in staging_dir/images/ but
the markdown may reference them without size attributes.  Different converters
treat image sizing differently:

  - docling  — extracts image files; no size hint in the MD references
  - inhouse  — may embed .jpx refs without dimensions
  - markitdown — skips images entirely for PDFs

This module provides a single public function:

    annotate_image_dimensions(staging_dir) -> int

It reads the actual pixel dimensions of each extracted image (via Pillow),
rewrites plain Markdown image references in index.md to HTML <img> tags with
width and height attributes, and writes an image_dimensions.json sidecar.

Returns the count of images that were annotated.

Converters that produce no images are a no-op (returns 0).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple


# Lazy PIL import so tests can still run without Pillow if they never call us
try:
    from PIL import Image as _PilImage
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False


class ImageDimensions(NamedTuple):
    width: int
    height: int


# Matches standard Markdown image syntax: ![alt text](path)
# The path may contain spaces; we capture lazily up to the closing paren.
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# Extensions we attempt to open with Pillow
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _read_dimensions(path: Path) -> ImageDimensions | None:
    """Return (width, height) for an image file, or None on failure."""
    if not _PIL_AVAILABLE:
        return None
    try:
        with _PilImage.open(path) as img:
            return ImageDimensions(*img.size)
    except Exception:
        return None


def _build_dimension_map(images_dir: Path) -> dict[str, ImageDimensions]:
    """
    Return {filename: (width, height)} for every readable image in images_dir.
    Keys are filenames only (not full paths).
    """
    result: dict[str, ImageDimensions] = {}
    if not images_dir.is_dir():
        return result
    for img_path in sorted(images_dir.iterdir()):
        if img_path.suffix.lower() in _IMAGE_EXTENSIONS:
            dims = _read_dimensions(img_path)
            if dims is not None:
                result[img_path.name] = dims
    return result


def _md_ref_to_html(alt: str, src: str, dims: ImageDimensions) -> str:
    """
    Convert a Markdown image reference to an HTML <img> tag with dimensions.

    We use width/height attributes so the renderer allocates space immediately
    without waiting for the image to load, and so LLM judges can see the size.
    """
    safe_alt = alt.replace('"', "&quot;")
    return f'<img src="{src}" alt="{safe_alt}" width="{dims.width}" height="{dims.height}">'


def _rewrite_markdown(content: str, dim_map: dict[str, ImageDimensions]) -> str:
    """
    Replace Markdown image references with HTML <img> tags where we have dimensions.

    Only references whose filename (basename of path) appears in dim_map are
    rewritten — unknowns are left untouched.
    """
    def _replace(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2).strip()
        filename = Path(src).name
        if filename in dim_map:
            return _md_ref_to_html(alt, src, dim_map[filename])
        return m.group(0)  # leave unchanged

    return _MD_IMAGE_RE.sub(_replace, content)


def annotate_image_dimensions(staging_dir: Path) -> int:
    """
    Annotate image references in staging_dir/index.md with pixel dimensions.

    Reads actual image files from staging_dir/images/ using Pillow, then
    rewrites Markdown image syntax to HTML <img> tags with width/height set.
    Also writes staging_dir/image_dimensions.json as a sidecar.

    Args:
        staging_dir: The method-scoped staging directory containing index.md
                     and (optionally) an images/ subdirectory.

    Returns:
        Number of images successfully annotated (0 if no images or no index.md).
    """
    index_md = staging_dir / "index.md"
    if not index_md.exists():
        return 0

    images_dir = staging_dir / "images"
    dim_map = _build_dimension_map(images_dir)

    if not dim_map:
        return 0

    # Write sidecar JSON (useful for downstream quality checks)
    sidecar = staging_dir / "image_dimensions.json"
    sidecar.write_text(
        json.dumps(
            {name: {"width": d.width, "height": d.height} for name, d in dim_map.items()},
            indent=2,
        ),
        encoding="utf-8",
    )

    content = index_md.read_text(encoding="utf-8", errors="replace")
    new_content = _rewrite_markdown(content, dim_map)

    if new_content != content:
        index_md.write_text(new_content, encoding="utf-8")

    # Count distinct image files whose references were annotated
    annotated = sum(
        1 for name in dim_map
        if name in new_content  # file appears at least once in the updated MD
    )
    return annotated
