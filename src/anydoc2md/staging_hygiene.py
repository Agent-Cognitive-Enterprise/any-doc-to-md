"""Adapter staging-directory hygiene for generated conversion artifacts.

`prepare_adapter_fixed_output_slot` clears stale generated outputs from a single
adapter staging directory so that a rerun into a reused directory cannot publish
a previous run's fixed output. It is meant to run after adapter conversion has
produced `index.md` and before any current-run paragraph repair, project-local
fix extension, selection, or publishing stage inspects the fixed-output slot.

`prepare_adapter_run_output_slot` runs before an adapter conversion starts so a
failed rerun cannot leave prior-run raw Markdown or images selectable. If an
adapter still leaves partial output while reporting failure,
`clear_failed_adapter_output` removes those selectable artifacts while preserving
the current failure sidecar when present.

Scope is deliberately narrow and local:

- raw adapter output (`index.md`, `images/`, generated image-dimension sidecar)
  is removed before a new adapter run and after a failed run, but unrelated
  files in the adapter directory are preserved,
- the shared `index_fixed.md` slot is removed unconditionally, because no current
  run has written it yet at guard time and nothing currently establishes
  ownership of a pre-existing one (any present file is therefore from a prior
  run); a later adapter that intentionally emits `index_fixed.md` would need an
  explicit ownership contract before selection could trust it,
- `prepare_adapter_fixed_output_slot` preserves a trusted current-run
  paragraph-repair candidate. The pre-run and failed-run helpers remove raw
  `index.md` first, so paragraph-repair artifacts are intentionally treated as
  stale and removed there,
- nothing outside the given directory is touched.
"""
from __future__ import annotations

from pathlib import Path

from anydoc2md.paragraph_repair.application import (
    INDEX_MD,
    PARAGRAPH_REPAIR_REPORT_JSON,
    PARAGRAPH_REPAIRED_MD,
    paragraph_repair_candidate_is_current,
)
from anydoc2md.path_hygiene import remove_path

ADAPTER_RESULT_JSON = "adapter_result.json"
IMAGE_DIMENSIONS_JSON = "image_dimensions.json"
IMAGES_DIR = "images"
INDEX_FIXED_MD = "index_fixed.md"


def prepare_adapter_run_output_slot(adapter_staging_dir: Path) -> None:
    """Clear generated outputs before one adapter starts a new conversion.

    A reused staging directory must not let prior-run raw Markdown, images, fixed
    output, or result sidecars masquerade as current-run artifacts if the adapter
    fails before rewriting them. Unknown files are preserved for inspection.
    """
    if not adapter_staging_dir.is_dir():
        return

    for filename in (
        INDEX_MD,
        IMAGES_DIR,
        IMAGE_DIMENSIONS_JSON,
        ADAPTER_RESULT_JSON,
    ):
        remove_path(adapter_staging_dir / filename)
    _remove_generated_fixed_output_artifacts(adapter_staging_dir)


def clear_failed_adapter_output(adapter_staging_dir: Path) -> None:
    """Remove selectable/publishable outputs left by a failed adapter run.

    Failed adapters may leave partial current-run files or stale prior-run files.
    Keep `adapter_result.json` when present so failure evidence remains available,
    but remove Markdown/assets that downstream gates, scoring, or publishing could
    otherwise treat as a valid candidate.
    """
    if not adapter_staging_dir.is_dir():
        return

    for filename in (INDEX_MD, IMAGES_DIR, IMAGE_DIMENSIONS_JSON):
        remove_path(adapter_staging_dir / filename)
    _remove_generated_fixed_output_artifacts(adapter_staging_dir)


def prepare_adapter_fixed_output_slot(adapter_staging_dir: Path) -> None:
    """Remove stale generated fixed-output artifacts from one adapter directory.

    Deterministic, local, and a no-op for a missing directory or a clean
    directory. Raw adapter output is preserved; see the module docstring for the
    exact removal policy.
    """
    if not adapter_staging_dir.is_dir():
        return

    _remove_generated_fixed_output_artifacts(adapter_staging_dir)


def _remove_generated_fixed_output_artifacts(adapter_staging_dir: Path) -> None:
    remove_path(adapter_staging_dir / INDEX_FIXED_MD)

    # In pre-run and failed-run cleanup, raw index.md has already been removed,
    # so no paragraph-repair candidate can be current and these owned artifacts
    # are cleared. In fixed-output-slot cleanup, a matching current-run candidate
    # is preserved for later composition.
    if not paragraph_repair_candidate_is_current(adapter_staging_dir):
        remove_path(adapter_staging_dir / PARAGRAPH_REPAIRED_MD)
        remove_path(adapter_staging_dir / PARAGRAPH_REPAIR_REPORT_JSON)
