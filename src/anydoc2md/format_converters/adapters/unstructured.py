"""
Unstructured adapter (Apache-2.0 via subprocess-backed Python integration).

This adapter uses the optional `unstructured` Python package to partition a
document into ordered elements, then renders those elements into conservative
Markdown for ADTM's staging layout.

Install: pip install 'unstructured[all-docs]'
"""
from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

from anydoc2md.format_converters.adapters.base import (
    AdapterResult,
    error_result,
    run_subprocess,
)

METHOD_NAME = "unstructured"
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".htm",
    ".html",
    ".json",
    ".md",
    ".odt",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rst",
    ".rtf",
    ".text",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
}


def _get_version() -> str:
    try:
        return metadata.version("unstructured")
    except metadata.PackageNotFoundError:
        return "not_installed"


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def run(
    source_path: Path,
    staging_dir: Path,
    *,
    timeout_s: int = 600,
) -> AdapterResult:
    """Convert source_path with unstructured, normalizing to staging layout."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "images").mkdir(exist_ok=True)

    version = _get_version()
    if version == "not_installed":
        return error_result(
            METHOD_NAME,
            version,
            "",
            staging_dir,
            0,
            "unstructured package not installed. Install with: "
            "pip install 'unstructured[all-docs]' and required system dependencies.",
            status="error",
        )

    if not supports(source_path):
        return error_result(
            METHOD_NAME,
            version,
            "",
            staging_dir,
            0,
            f"Unsupported extension: {source_path.suffix}",
            status="unsupported",
        )

    output_path = staging_dir / "index.md"
    cmd = [
        sys.executable,
        "-m",
        "anydoc2md.format_converters.adapters._unstructured_backend",
        "--input",
        str(source_path),
        "--output",
        str(output_path),
        "--images-dir",
        str(staging_dir / "images"),
    ]
    command_str = " ".join(cmd)
    exit_code, _stdout, stderr, timing_ms = run_subprocess(cmd, timeout_s=timeout_s)

    if exit_code == -2:
        return error_result(
            METHOD_NAME,
            version,
            command_str,
            staging_dir,
            timing_ms,
            stderr,
            exit_code=-2,
            status="timeout",
        )

    if exit_code != 0 or not output_path.exists():
        return error_result(
            METHOD_NAME,
            version,
            command_str,
            staging_dir,
            timing_ms,
            stderr or f"Exit code {exit_code}, no output file",
            exit_code=exit_code,
        )

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
