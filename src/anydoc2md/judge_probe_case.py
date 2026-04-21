"""Static fixture-backed probe case for testing LLM judge behavior."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import (
    DocumentTraits,
    classify,
)

EXPECTED_ISSUE_CLASSES = (
    "title formatting",
    "bullet list formatting",
    "numbered list formatting",
    "table fidelity",
    "figure caption mismatch",
)

_SOURCE_PDF_NAME = "probe_source_reference.pdf"
_CANDIDATE_PDF_NAME = "probe_candidate_broken.pdf"
_CANDIDATE_MD_NAME = "probe_candidate_broken.md"
_CANDIDATE_IMAGE_NAME = "probe_red_square.png"


@dataclass(frozen=True)
class ProbeCase:
    source_pdf: Path
    candidate_pdf: Path
    traits: DocumentTraits
    candidate: AdapterResult


def _asset_bytes(name: str) -> bytes:
    return files("anydoc2md").joinpath("probe_assets", name).read_bytes()


def _asset_text(name: str) -> str:
    return files("anydoc2md").joinpath("probe_assets", name).read_text(encoding="utf-8")


def build_probe_case(work_dir: Path) -> ProbeCase:
    source_pdf = work_dir / "source.pdf"
    candidate_pdf = work_dir / "candidate.pdf"
    source_pdf.write_bytes(_asset_bytes(_SOURCE_PDF_NAME))
    candidate_pdf.write_bytes(_asset_bytes(_CANDIDATE_PDF_NAME))

    traits = classify(source_pdf)

    staging_dir = work_dir / "candidate_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "index.md").write_text(_asset_text(_CANDIDATE_MD_NAME), encoding="utf-8")
    images_dir = staging_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (images_dir / _CANDIDATE_IMAGE_NAME).write_bytes(_asset_bytes(_CANDIDATE_IMAGE_NAME))

    candidate = AdapterResult(
        method_name="synthetic",
        method_version="0",
        command_invoked="",
        exit_code=0,
        staging_dir=staging_dir,
        timing_ms=0,
        status="ok",
    )
    return ProbeCase(
        source_pdf=source_pdf,
        candidate_pdf=candidate_pdf,
        traits=traits,
        candidate=candidate,
    )

