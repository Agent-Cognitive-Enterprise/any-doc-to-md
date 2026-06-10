"""
Tournament runner — run N adapters against one source document in parallel.

Usage:
    from anydoc2md.format_converters.tournament.runner import run_tournament

    results = run_tournament(source_path, staging_root)
    for r in results:
        print(r.method_name, r.status, r.timing_ms, "ms", len(r.markdown_text), "chars")
"""
from __future__ import annotations

import concurrent.futures
import importlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import ModuleType

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.staging_hygiene import (
    clear_failed_adapter_output,
    prepare_adapter_run_output_slot,
)

_THREAD_GRACE_S = 15  # extra seconds beyond timeout_s before a thread is declared hung

# Registry of implemented adapters (module path suffix → module).
_ADAPTER_MODULES: dict[str, str] = {
    "inhouse":    "anydoc2md.format_converters.adapters.inhouse",
    "markitdown": "anydoc2md.format_converters.adapters.markitdown",
    "docling":    "anydoc2md.format_converters.adapters.docling",
    "unstructured": "anydoc2md.format_converters.adapters.unstructured",
    "pandoc":     "anydoc2md.format_converters.adapters.pandoc",
    "marker":     "anydoc2md.format_converters.adapters.marker",
}


def available_adapter_names() -> list[str]:
    """Return all implemented adapters in stable registry order."""
    return list(_ADAPTER_MODULES)


DEFAULT_ADAPTERS = ["inhouse"]


def default_adapter_names() -> list[str]:
    """Return adapters used when the caller does not request an explicit set."""
    return list(DEFAULT_ADAPTERS)


def run_tournament(
    source_path: Path,
    staging_root: Path,
    adapters: list[str] | None = None,
    *,
    timeout_s: int = 600,
    max_workers: int = 4,
) -> list[AdapterResult]:
    """
    Run each adapter against source_path and return all AdapterResults.

    Args:
        source_path:  Source document to convert.
        staging_root: Root under which per-method dirs are created:
                      staging_root/{method_name}/
        adapters:     List of adapter names to run (default: inhouse only).
        timeout_s:    Per-adapter subprocess timeout (passed to each adapter).
        max_workers:  Thread pool size for parallel execution.

    Returns:
        List of AdapterResult, one per adapter, in completion order.
        Failed adapters produce error AdapterResults (status != "ok") — never raise.
    """
    names = default_adapter_names() if adapters is None else list(adapters)
    if not names:
        return []
    worker_count = max(1, min(max_workers, len(names)))
    results: list[AdapterResult] = []

    def _run_one(name: str) -> AdapterResult:
        staging_dir = staging_root / name
        staging_dir.mkdir(parents=True, exist_ok=True)
        prepare_adapter_run_output_slot(staging_dir)
        module = _load_adapter(name)
        try:
            return module.run(source_path, staging_dir, timeout_s=timeout_s)
        except TypeError:
            # Backward compatibility for adapters that haven't been updated yet.
            return module.run(source_path, staging_dir)

    wall_timeout = timeout_s + _THREAD_GRACE_S
    completed_names: set[str] = set()

    pool = ThreadPoolExecutor(max_workers=worker_count)
    futures = {pool.submit(_run_one, name): name for name in names}
    timed_out = False
    try:
        try:
            for future in concurrent.futures.as_completed(futures, timeout=wall_timeout):
                name = futures[future]
                completed_names.add(name)
                try:
                    result = future.result()
                except Exception as exc:
                    from anydoc2md.format_converters.adapters.base import error_result
                    clear_failed_adapter_output(staging_root / name)
                    results.append(error_result(
                        name, "unknown", "",
                        staging_root / name, 0,
                        f"Unhandled exception in adapter: {exc}",
                    ))
                    continue
                if not result.succeeded:
                    clear_failed_adapter_output(staging_root / name)
                    if result.staging_dir != staging_root / name:
                        result = replace(result, staging_dir=staging_root / name)
                results.append(result)
        except concurrent.futures.TimeoutError:
            timed_out = True
    finally:
        pool.shutdown(wait=not timed_out, cancel_futures=timed_out)

    from anydoc2md.format_converters.adapters.base import error_result
    for name in names:
        if name not in completed_names:
            clear_failed_adapter_output(staging_root / name)
            results.append(error_result(
                name, "unknown", "",
                staging_root / name, int(wall_timeout * 1000),
                f"Adapter did not complete within {wall_timeout}s wall-clock timeout",
                status="timeout",
            ))

    return results


def _load_adapter(name: str) -> ModuleType:
    module_path = _ADAPTER_MODULES.get(name)
    if module_path is None:
        raise ValueError(f"Unknown adapter: {name!r}. Available: {list(_ADAPTER_MODULES)}")
    return importlib.import_module(module_path)
