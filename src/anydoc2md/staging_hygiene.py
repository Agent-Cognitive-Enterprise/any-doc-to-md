"""Adapter staging-directory hygiene for generated fixed-output artifacts.

`prepare_adapter_fixed_output_slot` clears stale generated outputs from a single
adapter staging directory so that a rerun into a reused directory cannot publish
a previous run's fixed output. It is meant to run after adapter conversion has
produced `index.md` and before any current-run paragraph repair, project-local
fix extension, selection, or publishing stage inspects the fixed-output slot.

Scope is deliberately narrow and local:

- the shared `index_fixed.md` slot is removed unconditionally, because no current
  run has written it yet at guard time and nothing currently establishes
  ownership of a pre-existing one (any present file is therefore from a prior
  run); a later adapter that intentionally emits `index_fixed.md` would need an
  explicit ownership contract before selection could trust it,
- paragraph-repair artifacts (`index_paragraph_repaired.md` and its sidecar) are
  removed only when they are not a complete candidate matching the current raw
  `index.md` fingerprint; a trusted current-run candidate is preserved,
- raw adapter output (`index.md`, `images/`, adapter result JSON, ...) is never
  touched, and nothing outside the given directory is touched.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIR_REPORT_JSON,
    PARAGRAPH_REPAIRED_MD,
    paragraph_repair_candidate_is_current,
)

INDEX_FIXED_MD = "index_fixed.md"


def prepare_adapter_fixed_output_slot(adapter_staging_dir: Path) -> None:
    """Remove stale generated fixed-output artifacts from one adapter directory.

    Deterministic, local, and a no-op for a missing directory or a clean
    directory. Raw adapter output is preserved; see the module docstring for the
    exact removal policy.
    """
    if not adapter_staging_dir.is_dir():
        return

    _remove_path(adapter_staging_dir / INDEX_FIXED_MD)

    if not paragraph_repair_candidate_is_current(adapter_staging_dir):
        _remove_path(adapter_staging_dir / PARAGRAPH_REPAIRED_MD)
        _remove_path(adapter_staging_dir / PARAGRAPH_REPAIR_REPORT_JSON)


def _remove_path(path: Path) -> None:
    """Remove whatever is at `path` — file, symlink, or directory; no-op if absent.

    Downstream stages test the fixed-output slot with `Path.exists()`, which is
    true for a directory or symlink as well as a regular file, so the slot must
    be cleared regardless of node type. A symlink is unlinked without following
    it (the target is left untouched); a real directory is removed recursively.
    """
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
