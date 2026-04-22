"""Fixture builder for phase-2 freeform judge probing."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

_SOURCE_NOTES = """\
The source is a 7-page warehouse handover packet. A faithful conversion should:
- keep the title as "Warehouse Handover Packet";
- avoid repeating the running header "West Annex - Shift Handover" as document headings;
- keep the transfer steps in order: 1. Scan the dock marker. 2. Seal the amber tote.
  3. Attach the handover card. 4. Record the freezer reading. 5. Sign the turnover ledger.
  6. Store the tote in bay C;
- preserve the Shift Coverage Matrix as a real table with Shift / Lead / Backup / Verification;
- preserve Box 2 reminders including "Escalate any red tag older than 12 hours.";
- keep Figure 1 as "Amber square dock marker before sealing" near the image;
- keep image references resolvable with plausible dimensions;
- retain "Visitors must countersign the cold-room log.";
- retain "Record tamper-seal color in the ledger.".
"""
_SOURCE_PDF_NAME = "probe_freeform_source_reference.pdf"
_CANDIDATE_A_MD_NAME = "probe_freeform_candidate_a.md"


@dataclass(frozen=True)
class FreeformGoldIssue:
    issue_id: str
    required_term_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class FreeformProbeCase:
    case_id: str
    staging_dir: Path
    candidate_markdown: str
    min_expected_findings: int
    max_false_positives: int
    gold_issues: tuple[FreeformGoldIssue, ...]


@dataclass(frozen=True)
class FreeformProbeSuite:
    source_pdf: Path
    source_notes: str
    cases: tuple[FreeformProbeCase, ...]


def _asset_bytes(name: str) -> bytes:
    return files("anydoc2md").joinpath("probe_assets", name).read_bytes()


def _asset_text(name: str) -> str:
    return files("anydoc2md").joinpath("probe_assets", name).read_text(encoding="utf-8")


def _write_candidate_staging(
    *,
    root: Path,
    dir_name: str,
    markdown_name: str,
) -> Path:
    staging_dir = root / dir_name
    images_dir = staging_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "index.md").write_text(_asset_text(markdown_name), encoding="utf-8")
    return staging_dir


def _candidate_a_gold() -> tuple[FreeformGoldIssue, ...]:
    return (
        FreeformGoldIssue(
            "fragmented_title",
            (("warehouse",), ("handover",), ("packet",), ("title", "heading")),
        ),
        FreeformGoldIssue(
            "repeated_running_header",
            (("west annex - shift handover",), ("repeated", "running header", "header", "heading")),
        ),
        FreeformGoldIssue(
            "step_order_broken",
            (
                ("seal the amber tote",),
                ("attach the handover card",),
                ("scan the dock marker",),
            ),
        ),
        FreeformGoldIssue(
            "flattened_matrix",
            (("shift coverage matrix",), ("flattened", "bullets", "plain text", "lost columns")),
        ),
        FreeformGoldIssue(
            "missing_red_tag_rule",
            (("red tag older than 12 hours",), ("missing", "omitted", "lost", "not present")),
        ),
        FreeformGoldIssue(
            "broken_or_implausible_image_reference",
            (("missing-amber-square.png", "9999"),),
        ),
        FreeformGoldIssue(
            "wrong_caption",
            (
                ("blue marker after sealing",),
                ("amber square", "before sealing"),
            ),
        ),
        FreeformGoldIssue(
            "missing_tamper_seal_note",
            (("tamper-seal color",), ("missing", "omitted", "lost", "not present")),
        ),
    )

def build_freeform_probe_suite(work_dir: Path) -> FreeformProbeSuite:
    work_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = work_dir / "freeform_source.pdf"
    source_pdf.write_bytes(_asset_bytes(_SOURCE_PDF_NAME))

    case_a_dir = _write_candidate_staging(
        root=work_dir,
        dir_name="candidate_a_staging",
        markdown_name=_CANDIDATE_A_MD_NAME,
    )

    return FreeformProbeSuite(
        source_pdf=source_pdf,
        source_notes=_SOURCE_NOTES,
        cases=(
            FreeformProbeCase(
                case_id="candidate_a",
                staging_dir=case_a_dir,
                candidate_markdown=_asset_text(_CANDIDATE_A_MD_NAME),
                min_expected_findings=3,
                max_false_positives=2,
                gold_issues=_candidate_a_gold(),
            ),
        ),
    )


def freeform_gate_lines(suite: FreeformProbeSuite) -> tuple[str, ...]:
    lines = []
    for case in suite.cases:
        lines.append(
            f"{case.case_id}: find at least {case.min_expected_findings}/{len(case.gold_issues)} "
            f"gold issues with at most {case.max_false_positives} false positive(s)."
        )
    return tuple(lines)
