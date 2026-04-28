"""
HTML → Markdown converter.

Parses an HTML file with BeautifulSoup, converts structure to Markdown,
and downloads/copies all images into staging_dir/images/.

Overrides:
    base_url    str     override for resolving relative image URLs
    min_text_len int    10   discard text nodes shorter than this
    max_image_bytes int  8388608 max bytes to read for any one image
    allow_network_images bool False allow http(s) image downloads (disabled by default)
    allow_private_network_images bool False allow localhost/private-network image URLs
    allow_file_outside_html_dir bool False allow file:// images outside the HTML dir
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
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
    resolve_source_reference,
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
    default_base_url = source_url or (source_path.parent.as_uri() + "/")
    base_url: str = str(cfg.get("base_url", default_base_url))
    max_image_bytes: int = int(cfg.get("max_image_bytes", 8 * 1024 * 1024))
    allow_network_images: bool = bool(cfg.get("allow_network_images", False))
    allow_private_network_images: bool = bool(cfg.get("allow_private_network_images", False))
    allow_file_outside_html_dir: bool = bool(cfg.get("allow_file_outside_html_dir", False))

    html = source_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Use <title> if no explicit title provided
    resolved_title = title
    if not resolved_title:
        title_tag = soup.find("title")
        resolved_title = title_tag.get_text(strip=True) if title_tag else source_path.stem

    resolved_url = resolve_source_reference(source_path, source_url)

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()

    body = soup.find("body") or soup
    image_count = 0
    warnings: list[str] = []

    md_lines: list[str] = [f"# {resolved_title}\n", f"**Source:** {resolved_url}\n", ""]

    html_dir = source_path.parent.resolve()

    def _is_within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _is_disallowed_host(hostname: str) -> bool:
        lowered = hostname.lower().strip(".")
        if lowered in {"localhost"} or lowered.endswith(".localhost"):
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            )
        except ValueError:
            pass
        try:
            infos = socket.getaddrinfo(hostname, None)
        except OSError:
            return True
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                return True
        return False

    def _read_limited(resp, limit: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(min(64 * 1024, limit - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total >= limit:
                break
        return b"".join(chunks)

    def _fetch_image(src: str) -> str | None:
        """Download/copy image to images_dir, return relative path or None."""
        nonlocal image_count
        try:
            abs_url = urllib.parse.urljoin(base_url, src)
            if abs_url.startswith("file://"):
                img_path = Path(urllib.parse.unquote(abs_url[7:])).resolve()
                if not allow_file_outside_html_dir and not _is_within_root(img_path, html_dir):
                    warnings.append(
                        f"Skipping file:// image outside HTML directory: {src!r}"
                    )
                    return None
                try:
                    size = img_path.stat().st_size
                except OSError as exc:
                    warnings.append(f"Could not stat image {src!r}: {exc}")
                    return None
                if size > max_image_bytes:
                    warnings.append(f"Skipping large image {src!r}: {size} bytes")
                    return None
                img_bytes = img_path.read_bytes()
                ext = img_path.suffix or ".png"
            elif abs_url.startswith(("http://", "https://")):
                if not allow_network_images:
                    warnings.append(f"Skipping network image (disabled): {src!r}")
                    return None
                hostname = urllib.parse.urlparse(abs_url).hostname or ""
                if hostname and not allow_private_network_images and _is_disallowed_host(hostname):
                    warnings.append(f"Skipping disallowed network image host: {hostname}")
                    return None
                with urllib.request.urlopen(abs_url, timeout=15) as resp:
                    final_url = resp.geturl()
                    parsed = urllib.parse.urlparse(final_url)
                    if parsed.scheme not in {"http", "https"}:
                        warnings.append(f"Skipping redirected image URL: {final_url}")
                        return None
                    final_host = parsed.hostname or ""
                    if final_host and not allow_private_network_images and _is_disallowed_host(final_host):
                        warnings.append(f"Skipping redirected disallowed host: {final_host}")
                        return None
                    img_bytes = _read_limited(resp, max_image_bytes + 1)
                if len(img_bytes) > max_image_bytes:
                    warnings.append(f"Skipping large network image {src!r}: {len(img_bytes)} bytes")
                    return None
                ext = "." + abs_url.rsplit(".", 1)[-1].split("?")[0] if "." in abs_url else ".png"
            elif abs_url.startswith("data:"):
                # inline base64 — decode and save
                import base64
                header, data = abs_url.split(",", 1)
                mime = header.split(";")[0].split(":")[1]
                if not mime.startswith("image/"):
                    warnings.append(f"Skipping non-image data URI: {mime}")
                    return None
                ext = "." + mime.split("/")[-1]
                img_bytes = base64.b64decode(data)
                if len(img_bytes) > max_image_bytes:
                    warnings.append(f"Skipping large data URI image {src!r}: {len(img_bytes)} bytes")
                    return None
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
