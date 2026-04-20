"""
MarkItDown adapter (Microsoft, MIT licence).

CLI: markitdown <input> -o <output.md>

MarkItDown writes a flat Markdown file with no image extraction — images in
PDFs are silently skipped; references in DOCX/HTML may be inline base64 or
omitted.  The adapter normalises the output to the standard staging layout
(index.md, images/ dir created but may be empty).

Install: pip install markitdown
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

METHOD_NAME = "markitdown"
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".html", ".htm",
    ".txt", ".text", ".epub", ".zip",
}


def _get_version(cli: str) -> str:
    _, stdout, _, _ = run_subprocess([cli, "--version"], timeout_s=10)
    m = re.search(r"[\d]+\.[\d]+\.[\d.]+", stdout)
    return m.group(0) if m else "unknown"


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def run(source_path: Path, staging_dir: Path) -> AdapterResult:
    """Convert source_path with markitdown, writing index.md into staging_dir."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "images").mkdir(exist_ok=True)

    cli = find_cli("markitdown")
    if cli is None:
        return error_result(
            METHOD_NAME, "not_installed", "",
            staging_dir, 0,
            "markitdown CLI not found. Install with: pip install markitdown",
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
    output_path = staging_dir / "index.md"
    cmd = [cli, str(source_path), "-o", str(output_path)]
    command_str = " ".join(cmd)

    exit_code, _stdout, stderr, timing_ms = run_subprocess(cmd, timeout_s=300)

    if exit_code == -2:
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms, stderr, exit_code=-2, status="timeout",
        )

    if exit_code != 0 or not output_path.exists():
        return error_result(
            METHOD_NAME, version, command_str,
            staging_dir, timing_ms,
            stderr or f"Exit code {exit_code}, no output file",
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
