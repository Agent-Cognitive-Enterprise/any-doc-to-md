"""
Pandoc adapter (GPL-2.0+ via subprocess invocation).

CLI: pandoc -f <input-format> -t markdown <input> -o <output.md>

Pandoc is useful as a deterministic normalizer for structured text-centric
formats. It does not extract external image files into our staging layout, so
the adapter creates an empty images/ directory and relies on downstream checks
for any missing image references.
"""
from __future__ import annotations

import re
from pathlib import Path

from anydoc2md.format_converters.adapters.base import (
    AdapterResult,
    error_result,
    find_cli,
    run_subprocess,
)
from anydoc2md.format_converters.adapters.image_utils import annotate_image_dimensions

METHOD_NAME = "pandoc"
_INPUT_FORMATS = {
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "plain",
    ".text": "plain",
    ".rst": "rst",
    ".adoc": "asciidoc",
    ".asciidoc": "asciidoc",
}


def _get_version(cli: str) -> str:
    _, stdout, _, _ = run_subprocess([cli, "--version"], timeout_s=10)
    first_line = stdout.splitlines()[0] if stdout else ""
    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", first_line)
    return match.group(1) if match else "unknown"


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in _INPUT_FORMATS


def run(
    source_path: Path,
    staging_dir: Path,
    *,
    timeout_s: int = 300,
) -> AdapterResult:
    """Convert source_path with pandoc, writing index.md into staging_dir."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "images").mkdir(exist_ok=True)

    cli = find_cli("pandoc")
    if cli is None:
        return error_result(
            METHOD_NAME, "not_installed", "",
            staging_dir, 0,
            "pandoc CLI not found. Install pandoc and ensure it is on PATH.",
            status="error",
        )

    input_format = _INPUT_FORMATS.get(source_path.suffix.lower())
    version = _get_version(cli)
    if input_format is None:
        return error_result(
            METHOD_NAME, version, "",
            staging_dir, 0,
            f"Unsupported extension: {source_path.suffix}",
            status="unsupported",
        )

    output_path = staging_dir / "index.md"
    cmd = [
        cli,
        "-f", input_format,
        "-t", "markdown",
        str(source_path),
        "-o", str(output_path),
    ]
    command_str = " ".join(cmd)
    exit_code, _stdout, stderr, timing_ms = run_subprocess(cmd, timeout_s=timeout_s)

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
