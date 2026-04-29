"""Apply fix extensions incrementally to each adapter's output."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
from types import ModuleType

from anydoc2md.output_qa.runner import run_all
from anydoc2md.output_qa.scoring import build_scorecard


def apply_fix_extensions(
    adapter_name: str,
    adapter_staging_dir: Path,
    staging_root: Path,
    source_path: Path,
) -> None:
    """Apply staged fix extensions to one adapter's output.

    For each fix file (sorted): apply it to the current text, score the result,
    keep it only if the QA score strictly improves (lower is better). Fixes
    accumulate — each fix sees the output of the previous accepted fix.

    Writes index_fixed.md to adapter_staging_dir when at least one fix improved
    the score. Restores index.md to its original content regardless. Removes a
    stale index_fixed.md from a prior run when no fix improves the score.
    """
    index_md = adapter_staging_dir / "index.md"
    if not index_md.exists():
        return

    fix_files = _find_fix_files(staging_root)
    if not fix_files:
        return

    original_text = index_md.read_text(encoding="utf-8")

    base_report = run_all(adapter_staging_dir, source_path)
    base_score = build_scorecard(base_report, adapter_name).total_score

    current_text = original_text
    improved = False

    for fix_file in fix_files:
        index_md.write_text(current_text, encoding="utf-8")
        try:
            _run_fix_hook(fix_file, source_path, adapter_staging_dir, adapter_name)
        except Exception:
            index_md.write_text(current_text, encoding="utf-8")
            continue

        candidate_text = index_md.read_text(encoding="utf-8")
        try:
            candidate_report = run_all(adapter_staging_dir, source_path)
            candidate_score = build_scorecard(candidate_report, adapter_name).total_score
        except Exception:
            index_md.write_text(current_text, encoding="utf-8")
            continue

        if candidate_score < base_score:
            current_text = candidate_text
            improved = True
        else:
            index_md.write_text(current_text, encoding="utf-8")

    index_md.write_text(original_text, encoding="utf-8")

    fixed_file = adapter_staging_dir / "index_fixed.md"
    if improved:
        fixed_file.write_text(current_text, encoding="utf-8")
    elif fixed_file.exists():
        fixed_file.unlink()


def _find_fix_files(staging_root: Path) -> list[Path]:
    """Return the ordered list of fix extension files to apply.

    Component files (_*inhouse*.py) are preferred over the merged
    inhouse_extension.py when both exist — components allow per-file
    score guarding.
    """
    component_files = sorted(staging_root.glob("_*inhouse*.py"))
    if component_files:
        return component_files
    merged = staging_root / "inhouse_extension.py"
    return [merged] if merged.exists() else []


def _run_fix_hook(
    fix_file: Path,
    source_path: Path,
    staging_dir: Path,
    converter_name: str,
) -> None:
    module = _load_fix_module(fix_file)
    hook = getattr(module, "apply_inhouse_extension", None)
    if hook is None:
        raise ValueError(f"{fix_file.name} must define apply_inhouse_extension()")
    if not callable(hook):
        raise TypeError(f"{fix_file.name} apply_inhouse_extension is not callable")
    hook(source_path, staging_dir, converter_name)


def _load_fix_module(path: Path) -> ModuleType:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    module_name = f"anydoc2md_fix_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
