"""
Functional tests for anydoc2md.output_qa.checks and runner.

Tests cover each Layer 1 check individually, plus the QAReport.passed logic.
Layer 2 checks (image_count_match, text_coverage) are tested without real PDFs
— the checks gracefully return pass/warn when PyMuPDF not installed or source
is not a PDF.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md.output_qa.checks import (
    check_box_title_precedes_content,
    check_caption_near_image,
    check_heading_not_fragmented,
    check_image_count_match,
    check_image_size_plausible,
    check_images_locally_resolvable,
    check_no_double_bullets,
    check_no_repeated_headings,
    check_numbered_list_sequential,
    check_text_coverage,
)
from anydoc2md.output_qa.runner import QAReport, run_all


# ---------------------------------------------------------------------------
# check_no_double_bullets
# ---------------------------------------------------------------------------

def test_no_double_bullets_pass() -> None:
    md = "- Normal item\n- Another item\n"
    result = check_no_double_bullets(md)
    assert result.status == "pass"


def test_no_double_bullets_fail() -> None:
    md = "- • Bad item\n"
    result = check_no_double_bullets(md)
    assert result.status == "fail"
    assert result.layer == 1


# ---------------------------------------------------------------------------
# check_numbered_list_sequential
# ---------------------------------------------------------------------------

def test_numbered_list_sequential_pass() -> None:
    md = "1. First\n2. Second\n3. Third\n"
    result = check_numbered_list_sequential(md)
    assert result.status == "pass"


def test_numbered_list_sequential_fail_gap() -> None:
    md = "1. First\n3. Skipped\n4. Fourth\n"
    result = check_numbered_list_sequential(md)
    assert result.status == "fail"
    assert any("1 → 3" in d for d in result.details)


def test_numbered_list_sequential_single_item_passes() -> None:
    md = "1. Only one\n"
    result = check_numbered_list_sequential(md)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# check_heading_not_fragmented
# ---------------------------------------------------------------------------

def test_heading_not_fragmented_pass() -> None:
    md = "## Complete Heading\n\nParagraph text.\n"
    result = check_heading_not_fragmented(md)
    assert result.status == "pass"


def test_heading_not_fragmented_warn_on_lowercase_continuation() -> None:
    md = "## Heading\ncontinuation in lowercase\n"
    result = check_heading_not_fragmented(md)
    assert result.status == "warn"


def test_heading_not_fragmented_ok_when_next_line_uppercase() -> None:
    md = "## Heading\nUPPERCASE continuation is fine\n"
    result = check_heading_not_fragmented(md)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# check_caption_near_image
# ---------------------------------------------------------------------------

def test_caption_near_image_pass() -> None:
    md = (
        '<img src="images/fig1.png" style="width:10em" />\n'
        "*Figure 1. Caption text.*\n"
    )
    result = check_caption_near_image(md)
    assert result.status == "pass"


def test_caption_near_image_fail_when_far() -> None:
    filler = "\n".join(f"Line {i}" for i in range(20))
    md = "*Figure 1. Orphaned caption.*\n" + filler
    result = check_caption_near_image(md)
    assert result.status == "fail"


def test_caption_near_image_table_captions_ignored() -> None:
    """Table captions should NOT trigger caption_near_image failures."""
    md = "*Table 3.1. A table caption.*\n\nSome paragraph.\n"
    result = check_caption_near_image(md)
    assert result.status == "pass"


def test_caption_near_image_within_6_lines() -> None:
    """Caption within 6 lines of image should pass (window widened for stacked captions)."""
    lines = ['<img src="images/x.png" style="width:10em" />']
    lines += ["text line"] * 5
    lines += ["*Figure 2. Second caption.*"]
    md = "\n".join(lines)
    result = check_caption_near_image(md)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# check_box_title_precedes_content
# ---------------------------------------------------------------------------

def test_box_title_precedes_content_pass() -> None:
    md = "## Box 1. Title\n\nContent inside the box.\n"
    result = check_box_title_precedes_content(md)
    assert result.status == "pass"


def test_box_title_precedes_content_fail() -> None:
    md = "## Box 1. Title\n\n## Next heading immediately\n"
    result = check_box_title_precedes_content(md)
    assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_image_size_plausible
# ---------------------------------------------------------------------------

def test_image_size_plausible_pass() -> None:
    md = '<img src="images/x.png" style="width:20em" />\n'
    result = check_image_size_plausible(md)
    assert result.status == "pass"


def test_image_size_plausible_warn_oversize() -> None:
    md = '<img src="images/x.png" style="width:50em" />\n'
    result = check_image_size_plausible(md)
    assert result.status == "warn"


def test_image_size_plausible_warn_missing_width() -> None:
    md = '<img src="images/x.png" alt="no width" />\n'
    result = check_image_size_plausible(md)
    assert result.status == "warn"


# ---------------------------------------------------------------------------
# check_no_repeated_headings
# ---------------------------------------------------------------------------

def test_no_repeated_headings_pass() -> None:
    md = "## Introduction\n\n## Methods\n\n## Results\n"
    result = check_no_repeated_headings(md)
    assert result.status == "pass"


def test_no_repeated_headings_warn() -> None:
    md = "\n".join(
        ["## Running Header\n\nContent.\n"] * 3
    )
    result = check_no_repeated_headings(md)
    assert result.status == "warn"


# ---------------------------------------------------------------------------
# check_images_locally_resolvable
# ---------------------------------------------------------------------------

def test_images_locally_resolvable_pass(tmp_path: Path) -> None:
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "fig1.png").write_bytes(b"fake")
    md = '<img src="images/fig1.png" style="width:10em" />\n'
    result = check_images_locally_resolvable(md, tmp_path)
    assert result.status == "pass"


def test_images_locally_resolvable_fail_missing(tmp_path: Path) -> None:
    md = '<img src="images/missing.png" style="width:10em" />\n'
    result = check_images_locally_resolvable(md, tmp_path)
    assert result.status == "fail"
    assert "missing.png" in result.details[0]


def test_images_locally_resolvable_no_images_pass(tmp_path: Path) -> None:
    md = "Just text, no images.\n"
    result = check_images_locally_resolvable(md, tmp_path)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# Layer 2 — non-PDF source skips gracefully
# ---------------------------------------------------------------------------

def test_image_count_match_skips_non_pdf(tmp_path: Path) -> None:
    src = tmp_path / "doc.html"
    src.write_text("<html></html>")
    result = check_image_count_match("no images", src)
    assert result.status == "pass"
    assert "only implemented for PDF" in result.message


def test_text_coverage_skips_non_pdf(tmp_path: Path) -> None:
    src = tmp_path / "doc.txt"
    src.write_text("Some text")
    result = check_text_coverage("output", src)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# QAReport
# ---------------------------------------------------------------------------

def test_qa_report_passed_all_pass() -> None:
    from anydoc2md.output_qa.checks import CheckResult
    report = QAReport(
        staging_dir="/tmp/staging",
        source="",
        checks=[
            CheckResult("a", 1, "pass", "ok"),
            CheckResult("b", 1, "pass", "ok"),
        ],
    )
    assert report.passed is True


def test_qa_report_fails_on_any_fail() -> None:
    from anydoc2md.output_qa.checks import CheckResult
    report = QAReport(
        staging_dir="/tmp/staging",
        source="",
        checks=[
            CheckResult("a", 1, "pass", "ok"),
            CheckResult("b", 1, "fail", "bad"),
        ],
    )
    assert report.passed is False


def test_qa_report_passes_with_only_warns() -> None:
    from anydoc2md.output_qa.checks import CheckResult
    report = QAReport(
        staging_dir="/tmp/staging",
        source="",
        checks=[
            CheckResult("a", 1, "warn", "meh"),
        ],
    )
    assert report.passed is True


# ---------------------------------------------------------------------------
# run_all integration
# ---------------------------------------------------------------------------

def test_run_all_on_minimal_md(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.md").write_text("# Title\n\nParagraph.\n", encoding="utf-8")
    report = run_all(staging)
    assert isinstance(report.passed, bool)
    # All Layer 1 checks run — no failures for this clean minimal doc
    assert report.passed


def test_run_all_raises_when_no_index_md(tmp_path: Path) -> None:
    staging = tmp_path / "empty"
    staging.mkdir()
    with pytest.raises(FileNotFoundError):
        run_all(staging)


def test_run_all_to_dict_structure(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.md").write_text("# Title\n\nParagraph.\n", encoding="utf-8")
    report = run_all(staging)
    d = report.to_dict()
    assert "passed" in d
    assert "summary" in d
    assert "checks" in d
    assert d["summary"]["pass"] + d["summary"]["warn"] + d["summary"]["fail"] == len(report.checks)


def test_run_all_loads_parent_qa_extension(tmp_path: Path) -> None:
    doc_root = tmp_path / "doc"
    staging = doc_root / "inhouse"
    staging.mkdir(parents=True)
    (staging / "index.md").write_text("- • bad bullet\n", encoding="utf-8")
    (doc_root / "qa_extension.py").write_text(
        """
from anydoc2md.output_qa.checks import CheckResult

def get_disabled_checks():
    return ["check_no_double_bullets"]

def get_additional_md_only_checks():
    def custom_check(md_text):
        return CheckResult("custom_parent_extension", 1, "pass", "Loaded parent extension.")
    return [custom_check]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = run_all(staging)

    check_names = [check.name for check in report.checks]
    assert "no_double_bullets" not in check_names
    assert "custom_parent_extension" in check_names
