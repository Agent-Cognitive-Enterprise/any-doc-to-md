"""
Marker adapter (GPL-3.0 + model terms via subprocess invocation).

CLI: marker_single <input> --output_dir <dir> --output_format markdown

Marker is intended for layout-heavy PDFs. The adapter normalizes Marker output
into the shared staging layout:

- staging_dir/index.md
- staging_dir/images/
- staging_dir/adapter_result.json
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from anydoc2md.format_converters.adapters.base import (
    AdapterResult,
    error_result,
    find_cli,
    run_subprocess,
)
from anydoc2md.format_converters.adapters.image_utils import annotate_image_dimensions

METHOD_NAME = "marker"
SUPPORTED_EXTENSIONS = {".pdf"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _get_version(cli: str) -> str:
    _, stdout, _, _ = run_subprocess([cli, "--version"], timeout_s=10)
    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", stdout)
    return match.group(1) if match else "unknown"


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def run(source_path: Path, staging_dir: Path) -> AdapterResult:
    """Convert source_path with marker, normalizing output into staging layout."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    cli = find_cli("marker_single")
    if cli is None:
        return error_result(
            METHOD_NAME, "not_installed", "",
            staging_dir, 0,
            "marker_single CLI not found. Install marker and ensure it is on PATH.",
            status="error",
        )

    version = _get_version(cli)
    if not supports(source_path):
        return error_result(
            METHOD_NAME, version, "",
            staging_dir, 0,
            f"Unsupported extension: {source_path.suffix}",
            status="unsupported",
        )

    cmd = [
        cli,
        str(source_path),
        "--output_dir", str(staging_dir),
        "--output_format", "markdown",
    ]
    command_str = " ".join(cmd)
    exit_code, _stdout, stderr, timing_ms = run_subprocess(cmd, timeout_s=900)

    if exit_code == -2:
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms, stderr, exit_code=-2, status="timeout",
        )

    if exit_code != 0:
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms,
            stderr or f"Exit code {exit_code}",
            exit_code=exit_code,
        )

    _normalise_output(staging_dir)
    index_md = staging_dir / "index.md"
    if not index_md.exists():
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms,
            "No markdown output found after successful marker exit",
            exit_code=exit_code,
        )

    annotate_image_dimensions(staging_dir)

    result = AdapterResult(
        method_name=METHOD_NAME,
        method_version=version,
        command_invoked=command_str,
        exit_code=exit_code,
        staging_dir=staging_dir,
        timing_ms=timing_ms,
        status="ok",
        stderr=stderr,
    )
    result.save_result_json()
    return result


def _normalise_output(staging_dir: Path) -> None:
    """Move marker output into staging_dir/index.md and staging_dir/images/."""
    images_dir = staging_dir / "images"
    images_dir.mkdir(exist_ok=True)

    markdown_candidates = [
        path for path in staging_dir.rglob("*.md")
        if path.name != "index.md" or path.parent != staging_dir
    ]
    markdown_candidates.sort(key=lambda path: (len(path.parts), str(path)))

    if markdown_candidates:
        primary = markdown_candidates[0]
        if primary != staging_dir / "index.md":
            shutil.move(str(primary), str(staging_dir / "index.md"))

    path_rewrites: dict[str, str] = {}
    for path in sorted(staging_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.parent == images_dir or path.name in {"index.md", "adapter_result.json"}:
            continue
        if path.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue

        dest = images_dir / path.name
        if dest.exists():
            dest = images_dir / f"{path.parent.name}_{path.name}"
        old_rel = path.relative_to(staging_dir).as_posix()
        shutil.move(str(path), str(dest))
        path_rewrites[old_rel] = f"images/{dest.name}"

    index_md = staging_dir / "index.md"
    if index_md.exists() and path_rewrites:
        content = index_md.read_text(encoding="utf-8")
        for old_rel, new_rel in path_rewrites.items():
            content = content.replace(old_rel, new_rel)
        index_md.write_text(content, encoding="utf-8")
