"""
In-house adapter — wraps the existing format_converters (pdf/docx/html/txt).

This is a first-class tournament candidate, not a fallback.  It uses the same
staging_dir layout as external adapters so the tournament can treat all results
uniformly.
"""
from __future__ import annotations

import time
from pathlib import Path

from anydoc2md.format_converters import get_converter
from anydoc2md.format_converters.adapters.base import AdapterResult, error_result
from anydoc2md.format_converters.adapters.image_utils import annotate_image_dimensions

METHOD_NAME = "inhouse"
METHOD_VERSION = "1.0"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".html", ".htm", ".txt", ".text"}


def supports(source_path: Path) -> bool:
    return source_path.suffix.lower() in SUPPORTED_EXTENSIONS


def run(
    source_path: Path,
    staging_dir: Path,
    *,
    timeout_s: int = 0,
) -> AdapterResult:
    """
    Convert source_path using the existing in-house converter pipeline.

    Writes index.md + images/ into staging_dir.
    """
    _ = timeout_s  # in-house conversion is in-process; no subprocess timeout applies.
    staging_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    if not supports(source_path):
        return error_result(
            METHOD_NAME, METHOD_VERSION, "",
            staging_dir, 0,
            f"Unsupported extension: {source_path.suffix}",
            status="unsupported",
        )

    try:
        converter = get_converter(source_path)
        conversion_result = converter.convert(source_path, staging_dir)
        conversion_warnings = tuple(
            getattr(conversion_result, "warnings", ()) or ()
        )
        timing_ms = int((time.monotonic() - t0) * 1000)
    except Exception as exc:
        timing_ms = int((time.monotonic() - t0) * 1000)
        return error_result(
            METHOD_NAME, METHOD_VERSION,
            f"inhouse.convert({source_path.name})",
            staging_dir, timing_ms, str(exc),
        )

    annotate_image_dimensions(staging_dir)

    result = AdapterResult(
        method_name=METHOD_NAME,
        method_version=METHOD_VERSION,
        command_invoked=f"inhouse.convert({source_path.name})",
        exit_code=0,
        staging_dir=staging_dir,
        timing_ms=timing_ms,
        status="ok",
        warnings=conversion_warnings,
    )
    result.save_result_json()
    return result
