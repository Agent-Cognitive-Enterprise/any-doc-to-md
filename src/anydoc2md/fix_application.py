"""Apply fix extensions incrementally to each adapter's output."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
from types import ModuleType

from anydoc2md.output_qa.runner import run_all
from anydoc2md.output_qa.scoring import build_scorecard
from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIRED_MD,
    paragraph_repair_candidate_is_current,
)
from anydoc2md.staging_hygiene import remove_path


def apply_fix_extensions(
    adapter_name: str,
    adapter_staging_dir: Path,
    staging_root: Path,
    source_path: Path,
) -> None:
    """Apply staged fix extensions to one adapter's output.

    The starting "best text" is a trusted current-run paragraph-repair candidate
    (`index_paragraph_repaired.md`, validated by
    `paragraph_repair_candidate_is_current`) when one is present, otherwise the
    raw adapter `index.md`. Project-local fixes therefore build on built-in
    repair instead of discarding it.

    For each fix file (sorted): apply it to the current text, score the result,
    keep it only if the QA score strictly improves (lower is better). Fixes
    accumulate — each fix sees the output of the previous accepted fix.

    Writes index_fixed.md to adapter_staging_dir when at least one fix improved
    the score, or when a trusted repaired base was used (so built-in repair is
    promoted into the selectable fixed-output slot even if no fix improves it).
    Restores index.md to its original raw content regardless. Removes a stale
    index_fixed.md from a prior run when neither condition holds, including
    missing-index direct-call paths.
    """
    index_md = adapter_staging_dir / "index.md"
    fixed_file = adapter_staging_dir / "index_fixed.md"
    if not index_md.exists():
        remove_path(fixed_file)
        return

    original_text = index_md.read_text(encoding="utf-8")

    had_trusted_candidate = paragraph_repair_candidate_is_current(adapter_staging_dir)
    if had_trusted_candidate:
        base_text = (adapter_staging_dir / PARAGRAPH_REPAIRED_MD).read_text(encoding="utf-8")
    else:
        base_text = original_text

    fix_files = _find_fix_files(staging_root)
    if not fix_files:
        # No project-local fixes: this function owns index_fixed.md, so clear the
        # slot type-agnostically (file/symlink/stale directory), then promote a
        # trusted repaired base if one is present.
        remove_path(fixed_file)
        if had_trusted_candidate:
            fixed_file.write_text(base_text, encoding="utf-8")
        return

    # run_all scores index.md, so stage the base text there before scoring it
    # (a no-op when the base already is the raw index.md). The finally below
    # restores index.md to the raw original regardless of how this block exits,
    # including if base scoring raises while a repaired base is staged.
    current_text = base_text
    improved = False
    try:
        if had_trusted_candidate:
            index_md.write_text(base_text, encoding="utf-8")
        base_report = run_all(adapter_staging_dir, source_path)
        current_score = build_scorecard(base_report, adapter_name).total_score

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

            if candidate_score < current_score:
                current_text = candidate_text
                current_score = candidate_score
                improved = True
            else:
                index_md.write_text(current_text, encoding="utf-8")
    finally:
        index_md.write_text(original_text, encoding="utf-8")

    # Clear the slot type-agnostically (file/symlink/stale directory) before
    # promoting the chosen text, so a stale non-file slot cannot survive or make
    # the write raise for direct callers.
    remove_path(fixed_file)
    if improved or had_trusted_candidate:
        fixed_file.write_text(current_text, encoding="utf-8")


def _find_fix_files(staging_root: Path) -> list[Path]:
    """Return the ordered list of fix extension files to apply.

    Component files (_*fix*.py) are preferred over the merged
    fix_extension.py when both exist — components allow per-file
    score guarding.
    """
    component_files = sorted(staging_root.glob("_*fix*.py"))
    if component_files:
        return component_files
    merged = staging_root / "fix_extension.py"
    return [merged] if merged.exists() else []


def _run_fix_hook(
    fix_file: Path,
    source_path: Path,
    staging_dir: Path,
    converter_name: str,
) -> None:
    module = _load_fix_module(fix_file)
    hook = getattr(module, "apply_fix_extension", None)
    if hook is None:
        raise ValueError(f"{fix_file.name} must define apply_fix_extension()")
    if not callable(hook):
        raise TypeError(f"{fix_file.name} apply_fix_extension is not callable")
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
