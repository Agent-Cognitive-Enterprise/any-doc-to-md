"""
HTML → Markdown converter.

Parses an HTML file with BeautifulSoup, converts structure to Markdown,
and downloads/copies all images into staging_dir/images/.

Overrides:
    base_url    str     override for resolving relative image URLs
    min_text_len int    10   discard text nodes shorter than this
"""
from __future__ import annotations

import hashlib
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from anydoc2md.format_converters.base import (
    IMAGES_DIRNAME,
    INDEX_FILENAME,
    ConversionResult,
    load_overrides,
)

SUPPORTED_EXTENSIONS = {".html", ".htm"}

_WHITESPACE_RE = re.compile(r"\s+")


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def convert(
    source_path: Path,
    staging_dir: Path,
    *,
    title: str = "",
    source_url: str = "",
    overrides: dict[str, Any] | None = None,
) -> ConversionResult:
    staging_dir.mkdir(parents=True, exist_ok=True)
    images_dir = staging_dir / IMAGES_DIRNAME
    images_dir.mkdir(exist_ok=True)

    cfg = load_overrides(staging_dir, overrides)
    min_text_len: int = int(cfg.get("min_text_len", 10))
    base_url: str = str(cfg.get("base_url", source_url or source_path.parent.as_uri()))

    html = source_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Use <title> if no explicit title provided
    resolved_title = title
    if not resolved_title:
        title_tag = soup.find("title")
        resolved_title = title_tag.get_text(strip=True) if title_tag else source_path.stem

    resolved_url = source_url or f"file://{source_path.resolve()}"

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()

    body = soup.find("body") or soup
    image_count = 0
    warnings: list[str] = []

    md_lines: list[str] = [f"# {resolved_title}\n", f"**Source:** {resolved_url}\n", ""]

    def _fetch_image(src: str) -> str | None:
        """Download/copy image to images_dir, return relative path or None."""
        nonlocal image_count
        try:
            abs_url = urllib.parse.urljoin(base_url, src)
            if abs_url.startswith("file://"):
                img_path = Path(urllib.parse.unquote(abs_url[7:]))
                img_bytes = img_path.read_bytes()
                ext = img_path.suffix or ".png"
            elif abs_url.startswith(("http://", "https://")):
                with urllib.request.urlopen(abs_url, timeout=15) as resp:
                    img_bytes = resp.read()
                ext = "." + abs_url.rsplit(".", 1)[-1].split("?")[0] if "." in abs_url else ".png"
            elif abs_url.startswith("data:"):
                # inline base64 — decode and save
                import base64
                header, data = abs_url.split(",", 1)
                mime = header.split(";")[0].split(":")[1]
                ext = "." + mime.split("/")[-1]
                img_bytes = base64.b64decode(data)
            else:
                return None

            img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
            filename = f"img_{img_hash}{ext}"
            (images_dir / filename).write_bytes(img_bytes)
            image_count += 1
            return f"{IMAGES_DIRNAME}/{filename}"
        except Exception as exc:
            warnings.append(f"Could not fetch image {src!r}: {exc}")
            return None

    def _walk(node: Tag) -> None:
        if isinstance(node, NavigableString):
            text = _WHITESPACE_RE.sub(" ", str(node)).strip()
            if len(text) >= min_text_len:
                md_lines.append(text + "\n")
            return

        tag = node.name.lower() if node.name else ""

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            prefix = "#" * min(level, 3)
            text = " ".join(node.get_text().split())
            if text:
                md_lines.append(f"{prefix} {text}\n")

        elif tag == "p":
            text = " ".join(node.get_text().split())
            if len(text) >= min_text_len:
                md_lines.append(text + "\n")

        elif tag in ("ul", "ol"):
            for i, li in enumerate(node.find_all("li", recursive=False), start=1):
                text = " ".join(li.get_text().split())
                if not text:
                    continue
                prefix = f"{i}." if tag == "ol" else "-"
                md_lines.append(f"{prefix} {text}\n")

        elif tag == "img":
            src = node.get("src", "")
            alt = node.get("alt", "")
            if src:
                rel = _fetch_image(src)
                if rel:
                    # Estimate display width: use width attr if present, else full-width
                    w_attr = node.get("width")
                    w_em = f"{min(float(w_attr) / 16, 38):.1f}" if w_attr else "38.0"
                    md_lines.append(
                        f'<img src="{rel}" alt="{alt}"'
                        f' style="width: {w_em}em; max-width: 100%; display: block; margin: 0.5em 0;" />\n'
                    )

        elif tag in ("figure",):
            for child in node.children:
                _walk(child)

        elif tag == "figcaption":
            text = " ".join(node.get_text().split())
            if text:
                md_lines.append(f"*{text}*\n")

        elif tag in ("table",):
            md_lines.append(f"```\n{node.get_text()}\n```\n")

        elif tag in ("br",):
            md_lines.append("\n")

        elif tag in ("div", "section", "article", "main", "aside", "figure"):
            for child in node.children:
                _walk(child)

        elif tag in ("strong", "b", "em", "i", "span", "a"):
            text = " ".join(node.get_text().split())
            if len(text) >= min_text_len:
                md_lines.append(text + "\n")

        else:
            for child in node.children:
                _walk(child)

    for child in body.children:
        _walk(child)

    md = "\n".join(md_lines)
    (staging_dir / INDEX_FILENAME).write_text(md, encoding="utf-8")

    return ConversionResult(
        staging_dir=staging_dir,
        title=resolved_title,
        source_url=resolved_url,
        image_count=image_count,
        warnings=tuple(warnings),
    )
