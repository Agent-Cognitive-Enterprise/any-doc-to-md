"""
Shared types for format converters.

Every converter writes to a staging directory with a predictable layout:

    staging_dir/
        index.md          ← converted Markdown
        images/           ← extracted/downloaded images referenced in index.md
        document.override.yaml  ← optional, read automatically on convert()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from anydoc2md.project_extensions import resolve_override_path

OVERRIDE_FILENAME = "document.override.yaml"
INDEX_FILENAME = "index.md"
IMAGES_DIRNAME = "images"


@dataclass(frozen=True)
class ConversionResult:
    staging_dir: Path
    title: str
    source_url: str
    image_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def index_md(self) -> Path:
        return self.staging_dir / INDEX_FILENAME

    @property
    def images_dir(self) -> Path:
        return self.staging_dir / IMAGES_DIRNAME


def load_overrides(staging_dir: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Load document.override.yaml from staging_dir or its parent document root
    (if present) and merge with any explicitly supplied overrides. Explicit
    overrides win on conflict.
    """
    overrides: dict[str, Any] = {}
    override_path = resolve_override_path(staging_dir, OVERRIDE_FILENAME)
    if override_path is not None:
        raw = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            overrides.update(raw)
    if extra:
        overrides.update(extra)
    return overrides


def resolve_source_reference(source_path: Path, explicit_source_url: str = "") -> str:
    """
    Return source metadata safe to write into generated Markdown.

    Explicit source URLs are preserved because the caller chose to publish them.
    The implicit fallback is only the filename, not an absolute local file:// URI.
    """
    return explicit_source_url or source_path.name
