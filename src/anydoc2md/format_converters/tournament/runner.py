"""
Tournament runner — run N adapters against one source document in parallel.

Usage:
    from anydoc2md.format_converters.tournament.runner import run_tournament

    results = run_tournament(
        source_path,
        staging_root,
        adapters=["inhouse", "markitdown", "docling"],
    )
    for r in results:
        print(r.method_name, r.status, r.timing_ms, "ms", len(r.markdown_text), "chars")
"""
from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import ModuleType

from anydoc2md.format_converters.adapters.base import AdapterResult

# Registry of implemented adapters (module path suffix → module).
# Planned adapters such as pandoc/marker stay out of the runtime registry
# until their modules actually ship, so docs and behavior stay aligned.
_ADAPTER_MODULES: dict[str, str] = {
    "inhouse":    "anydoc2md.format_converters.adapters.inhouse",
    "markitdown": "anydoc2md.format_converters.adapters.markitdown",
    "docling":    "anydoc2md.format_converters.adapters.docling",
    "pandoc":     "anydoc2md.format_converters.adapters.pandoc",
    "marker":     "anydoc2md.format_converters.adapters.marker",
}

DEFAULT_ADAPTERS = ["inhouse", "markitdown", "docling"]


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
        adapters:     List of adapter names to run (default: inhouse, markitdown, docling).
        timeout_s:    Per-adapter subprocess timeout (passed to each adapter).
        max_workers:  Thread pool size for parallel execution.

    Returns:
        List of AdapterResult, one per adapter, in completion order.
        Failed adapters produce error AdapterResults (status != "ok") — never raise.
    """
    names = adapters or DEFAULT_ADAPTERS
    results: list[AdapterResult] = []

    def _run_one(name: str) -> AdapterResult:
        module = _load_adapter(name)
        staging_dir = staging_root / name
        staging_dir.mkdir(parents=True, exist_ok=True)
        return module.run(source_path, staging_dir)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(names))) as pool:
        futures = {pool.submit(_run_one, name): name for name in names}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                name = futures[future]
                from anydoc2md.format_converters.adapters.base import error_result
                results.append(error_result(
                    name, "unknown", "",
                    staging_root / name, 0,
                    f"Unhandled exception in adapter: {exc}",
                ))

    return results


def _load_adapter(name: str) -> ModuleType:
    module_path = _ADAPTER_MODULES.get(name)
    if module_path is None:
        raise ValueError(f"Unknown adapter: {name!r}. Available: {list(_ADAPTER_MODULES)}")
    return importlib.import_module(module_path)
