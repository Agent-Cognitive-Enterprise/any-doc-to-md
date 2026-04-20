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
    Load document.override.yaml from staging_dir (if present) and merge with
    any explicitly supplied overrides.  Explicit overrides win on conflict.
    """
    overrides: dict[str, Any] = {}
    override_path = staging_dir / OVERRIDE_FILENAME
    if override_path.exists():
        raw = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            overrides.update(raw)
    if extra:
        overrides.update(extra)
    return overrides
