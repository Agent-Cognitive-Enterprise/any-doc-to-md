"""
Docling adapter (IBM / docling-project, MIT licence).

CLI: docling <input> --to md --output <dir>

Docling writes <stem>.md + an assets/ dir containing extracted images.
This adapter renames the output to index.md and moves assets/ → images/
to match the standard staging layout.

Install: pip install docling
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

METHOD_NAME = "docling"
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx",
    ".html", ".htm", ".md", ".asciidoc", ".txt",
}


def _get_version(cli: str) -> str:
    _, stdout, _, _ = run_subprocess([cli, "--version"], timeout_s=10)
    m = re.search(r"[\d]+\.[\d]+\.[\d.]+", stdout)
    return m.group(0) if m else "unknown"


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def run(source_path: Path, staging_dir: Path) -> AdapterResult:
    """Convert source_path with docling, normalising output to staging layout."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    cli = find_cli("docling")
    if cli is None:
        return error_result(
            METHOD_NAME, "not_installed", "",
            staging_dir, 0,
            "docling CLI not found. Install with: pip install docling",
            status="error",
        )

    if not supports(source_path):
        return error_result(
            METHOD_NAME, _get_version(cli), "",
            staging_dir, 0,
            f"Unsupported extension: {source_path.suffix}",
            status="unsupported",
        )

    version = _get_version(cli)
    cmd = [
        cli, str(source_path),
        "--to", "md",
        "--output", str(staging_dir),
        "--image-export-mode", "referenced",   # write images as files, not base64
    ]
    command_str = " ".join(cmd)

    exit_code, _stdout, stderr, timing_ms = run_subprocess(cmd, timeout_s=600)

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

    # Docling writes <stem>.md — find it and rename to index.md
    md_files = list(staging_dir.glob("*.md"))
    if not md_files:
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms,
            "No .md file found in output dir after successful exit",
            exit_code=exit_code,
        )

    primary_md = md_files[0]
    if primary_md.name != "index.md":
        primary_md.rename(staging_dir / "index.md")

    # Docling may write images into <stem>_artifacts/ or similar — move to images/
    _normalise_assets(staging_dir, source_path.stem)

    # Annotate image references with actual pixel dimensions
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


def _normalise_assets(staging_dir: Path, stem: str) -> None:
    """
    Move docling image output into staging_dir/images/ and rewrite paths in index.md.

    Docling may produce:
      - {stem}_artifacts/   — typical output dir containing image files
      - images/             — if --image-export-mode referenced already wrote here

    After moving, every reference to the old relative path in index.md is
    rewritten to images/<filename> so links remain valid.
    """
    images_dir = staging_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Map old_rel_path → new filename for MD rewriting
    path_rewrites: dict[str, str] = {}

    for candidate in staging_dir.iterdir():
        if candidate.is_dir() and candidate.name not in {"images"}:
            for img in sorted(candidate.iterdir()):
                if img.is_file():
                    dest = images_dir / img.name
                    # Avoid name collision
                    if dest.exists():
                        dest = images_dir / f"{candidate.name}_{img.name}"
                    shutil.move(str(img), str(dest))
                    # Record rewrite: old relative path as it appears in MD
                    old_rel = f"{candidate.name}/{img.name}"
                    path_rewrites[old_rel] = f"images/{dest.name}"
            try:
                candidate.rmdir()
            except OSError:
                pass  # not fully empty — leave it

    if not path_rewrites:
        return

    # Rewrite index.md references
    index_md = staging_dir / "index.md"
    if not index_md.exists():
        return

    content = index_md.read_text(encoding="utf-8")
    for old_rel, new_rel in path_rewrites.items():
        content = content.replace(old_rel, new_rel)
    index_md.write_text(content, encoding="utf-8")
