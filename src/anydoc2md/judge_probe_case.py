"""Synthetic PDF/Markdown probe case for testing LLM judge behavior."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import fitz

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import (
    DocumentTraits,
    classify,
)

INTRO_MARKER = "INTRO_MARKER_7F3A"
STEP_ONE_MARKER = "STEP_ONE_MARKER_9A1C"
STEP_TWO_MARKER = "STEP_TWO_MARKER_B52D"
FIGURE_MARKER = "FIGURE_MARKER_C1D0"
REQUIRED_MARKERS = (INTRO_MARKER, STEP_ONE_MARKER, STEP_TWO_MARKER, FIGURE_MARKER)

# 1x1 PNG (opaque red) so we can embed an actual image without extra deps.
RED_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@dataclass(frozen=True)
class ProbeCase:
    source_pdf: Path
    candidate_pdf: Path
    traits: DocumentTraits
    candidate: AdapterResult


def _write_probe_pdf(path: Path, *, candidate: bool) -> None:
    title = "ADTM Judge Probe"
    marker_line = (
        f"Markers: {INTRO_MARKER}, {STEP_ONE_MARKER}, {STEP_TWO_MARKER}, {FIGURE_MARKER}."
    )
    instruction_line = (
        "Instruction: When reporting issues, quote marker IDs exactly as written."
    )

    if candidate:
        intro = f"{INTRO_MARKER}: Wash hands AFTER donning gloves."
        steps = [
            f"2. {STEP_TWO_MARKER}: Start procedure.",
            f"1. {STEP_ONE_MARKER}: Put on gloves.",
        ]
        caption = f"Figure 1 ({FIGURE_MARKER}): Red square is next to Step 2."
    else:
        intro = f"{INTRO_MARKER}: Wash hands BEFORE donning gloves."
        steps = [
            f"1. {STEP_ONE_MARKER}: Put on gloves.",
            f"2. {STEP_TWO_MARKER}: Start procedure.",
        ]
        caption = f"Figure 1 ({FIGURE_MARKER}): Red square is next to Step 1."

    doc = fitz.open()
    try:
        page1 = doc.new_page()
        y = 72
        page1.insert_text((72, y), title, fontsize=18)
        y += 26
        page1.insert_text((72, y), marker_line, fontsize=10)
        y += 14
        page1.insert_text((72, y), instruction_line, fontsize=10)
        y += 22
        page1.insert_text((72, y), intro, fontsize=12)
        y += 22
        for line in steps:
            page1.insert_text((72, y), line, fontsize=12)
            y += 18

        page2 = doc.new_page()
        page2.insert_text((72, 72), "Figure section", fontsize=14)
        rect = fitz.Rect(72, 110, 220, 260)
        page2.insert_image(rect, stream=RED_PNG_BYTES)
        page2.insert_text((72, 275), caption, fontsize=11)
        page2.insert_text(
            (72, 300),
            f"Reference: see {FIGURE_MARKER} for visual context.",
            fontsize=11,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(path))
    finally:
        doc.close()


def _write_candidate_markdown(path: Path) -> None:
    md = "\n".join(
        [
            "# ADTM Judge Probe",
            "",
            f"Markers: {INTRO_MARKER}, {STEP_ONE_MARKER}, {STEP_TWO_MARKER}, {FIGURE_MARKER}.",
            "",
            f"{INTRO_MARKER}: Wash hands AFTER donning gloves.",
            "",
            f"2. {STEP_TWO_MARKER}: Start procedure.",
            f"1. {STEP_ONE_MARKER}: Put on gloves.",
            "",
            "![red square](images/red.png)",
            "",
            f"Figure 1 ({FIGURE_MARKER}): Red square is next to Step 2.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")


def build_probe_case(work_dir: Path) -> ProbeCase:
    source_pdf = work_dir / "source.pdf"
    candidate_pdf = work_dir / "candidate.pdf"
    _write_probe_pdf(source_pdf, candidate=False)
    _write_probe_pdf(candidate_pdf, candidate=True)

    traits = classify(source_pdf)

    staging_dir = work_dir / "candidate_staging"
    _write_candidate_markdown(staging_dir / "index.md")
    (staging_dir / "images").mkdir(parents=True, exist_ok=True)
    (staging_dir / "images" / "red.png").write_bytes(RED_PNG_BYTES)

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

