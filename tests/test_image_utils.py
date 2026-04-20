"""
Tests for format_converters/adapters/image_utils.py.

Verifies that annotate_image_dimensions():
  - is a no-op when there is no index.md
  - is a no-op when images/ is empty or absent
  - reads actual pixel dimensions from image files
  - rewrites Markdown image refs to HTML <img> tags with width/height
  - leaves refs whose basename is not in images/ unchanged
  - writes image_dimensions.json sidecar
  - handles duplicate alt text and special characters in alt text
  - returns correct count of annotated images
"""
from __future__ import annotations

import io
import json
import struct
import zlib
from pathlib import Path

import pytest

from anydoc2md.format_converters.adapters.image_utils import (
    annotate_image_dimensions,
    _build_dimension_map,
    _rewrite_markdown,
    ImageDimensions,
)


# =========================================================================== #
# Helpers — minimal valid image files created without heavy deps
# =========================================================================== #

def _write_png(path: Path, width: int, height: int) -> None:
    """Write the smallest valid PNG at the given dimensions."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\x00\x00\x00" * width
    idat_data = zlib.compress(scanline * height)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat_data)
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _staging(tmp_path: Path, md_content: str = "") -> Path:
    """Create a staging dir with index.md and empty images/."""
    d = tmp_path / "staging"
    d.mkdir()
    (d / "images").mkdir()
    (d / "index.md").write_text(md_content, encoding="utf-8")
    return d


# =========================================================================== #
# _build_dimension_map
# =========================================================================== #

class TestBuildDimensionMap:
    def test_empty_images_dir(self, tmp_path: Path) -> None:
        images = tmp_path / "images"
        images.mkdir()
        assert _build_dimension_map(images) == {}

    def test_absent_images_dir(self, tmp_path: Path) -> None:
        assert _build_dimension_map(tmp_path / "no_images") == {}

    def test_reads_png_dimensions(self, tmp_path: Path) -> None:
        images = tmp_path / "images"
        images.mkdir()
        _write_png(images / "fig.png", 320, 240)
        result = _build_dimension_map(images)
        assert result["fig.png"] == ImageDimensions(320, 240)

    def test_reads_multiple_pngs(self, tmp_path: Path) -> None:
        images = tmp_path / "images"
        images.mkdir()
        _write_png(images / "a.png", 100, 50)
        _write_png(images / "b.png", 200, 150)
        result = _build_dimension_map(images)
        assert result["a.png"] == ImageDimensions(100, 50)
        assert result["b.png"] == ImageDimensions(200, 150)

    def test_ignores_non_image_files(self, tmp_path: Path) -> None:
        images = tmp_path / "images"
        images.mkdir()
        (images / "notes.txt").write_text("hello")
        (images / "data.json").write_text("{}")
        assert _build_dimension_map(images) == {}

    def test_ignores_corrupt_image(self, tmp_path: Path) -> None:
        images = tmp_path / "images"
        images.mkdir()
        (images / "bad.png").write_bytes(b"not a png")
        # Should return empty rather than raise
        assert _build_dimension_map(images) == {}


# =========================================================================== #
# _rewrite_markdown
# =========================================================================== #

class TestRewriteMarkdown:
    def test_rewrites_known_image(self) -> None:
        dim_map = {"fig.png": ImageDimensions(800, 600)}
        md = "# Title\n\n![A figure](images/fig.png)\n\nText."
        result = _rewrite_markdown(md, dim_map)
        assert '<img src="images/fig.png" alt="A figure" width="800" height="600">' in result
        assert "![A figure]" not in result

    def test_leaves_unknown_image_unchanged(self) -> None:
        dim_map = {"other.png": ImageDimensions(100, 100)}
        md = "![Missing](images/missing.png)"
        assert _rewrite_markdown(md, dim_map) == md

    def test_rewrites_multiple_images(self) -> None:
        dim_map = {
            "a.png": ImageDimensions(400, 300),
            "b.png": ImageDimensions(640, 480),
        }
        md = "![One](images/a.png)\n\n![Two](images/b.png)"
        result = _rewrite_markdown(md, dim_map)
        assert 'width="400" height="300"' in result
        assert 'width="640" height="480"' in result

    def test_handles_empty_alt_text(self) -> None:
        dim_map = {"fig.png": ImageDimensions(10, 10)}
        md = "![](images/fig.png)"
        result = _rewrite_markdown(md, dim_map)
        assert 'alt=""' in result

    def test_escapes_quotes_in_alt(self) -> None:
        dim_map = {"fig.png": ImageDimensions(10, 10)}
        md = '!["quoted" alt](images/fig.png)'
        result = _rewrite_markdown(md, dim_map)
        assert "&quot;" in result
        assert '"quoted"' not in result.split("alt=")[1].split(">")[0]

    def test_no_change_when_dim_map_empty(self) -> None:
        md = "![img](images/fig.png)"
        assert _rewrite_markdown(md, {}) == md


# =========================================================================== #
# annotate_image_dimensions (integration)
# =========================================================================== #

class TestAnnotateImageDimensions:
    def test_no_op_when_no_index_md(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "images").mkdir()
        assert annotate_image_dimensions(staging) == 0

    def test_no_op_when_no_images(self, tmp_path: Path) -> None:
        staging = _staging(tmp_path, md_content="![fig](images/fig.png)")
        # images/ exists but is empty
        assert annotate_image_dimensions(staging) == 0
        # index.md must be unchanged
        assert "![fig]" in (staging / "index.md").read_text()

    def test_rewrites_md_and_returns_count(self, tmp_path: Path) -> None:
        staging = _staging(tmp_path, md_content="# H\n\n![Chart](images/chart.png)\n")
        _write_png(staging / "images" / "chart.png", 500, 300)
        count = annotate_image_dimensions(staging)
        assert count == 1
        content = (staging / "index.md").read_text()
        assert '<img src="images/chart.png"' in content
        assert 'width="500"' in content
        assert 'height="300"' in content

    def test_writes_sidecar_json(self, tmp_path: Path) -> None:
        staging = _staging(tmp_path, md_content="![x](images/x.png)")
        _write_png(staging / "images" / "x.png", 100, 200)
        annotate_image_dimensions(staging)
        sidecar = staging / "image_dimensions.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text())
        assert data["x.png"] == {"width": 100, "height": 200}

    def test_mixed_known_and_unknown_refs(self, tmp_path: Path) -> None:
        md = "![A](images/known.png)\n\n![B](images/unknown.png)"
        staging = _staging(tmp_path, md_content=md)
        _write_png(staging / "images" / "known.png", 256, 128)
        count = annotate_image_dimensions(staging)
        content = (staging / "index.md").read_text()
        assert count == 1
        assert '<img src="images/known.png"' in content
        assert "![B](images/unknown.png)" in content  # untouched

    def test_count_is_unique_refs_not_occurrences(self, tmp_path: Path) -> None:
        # Same image referenced twice — should count as 1 unique ref annotated
        md = "![A](images/fig.png)\n\n![A again](images/fig.png)"
        staging = _staging(tmp_path, md_content=md)
        _write_png(staging / "images" / "fig.png", 64, 64)
        count = annotate_image_dimensions(staging)
        # Both occurrences are rewritten; unique src count = 1
        assert count == 1

    def test_no_images_dir(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "index.md").write_text("![img](images/fig.png)")
        # No images/ dir at all — should not raise
        assert annotate_image_dimensions(staging) == 0
