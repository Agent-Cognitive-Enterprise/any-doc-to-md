from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md.output_qa.checks import (
    CheckResult,
    check_caption_near_image,
    check_images_locally_resolvable,
    check_no_double_bullets,
    check_paragraph_not_row_sliced,
    check_text_coverage,
)
from anydoc2md.output_qa.scoring import score_check


def test_check_result_to_dict_omits_empty_structured_violation_fields() -> None:
    payload = CheckResult("plain_check", 1, "pass", "ok").to_dict()

    assert payload == {
        "name": "plain_check",
        "layer": 1,
        "status": "pass",
        "message": "ok",
        "details": [],
    }


def test_check_result_to_dict_includes_structured_violation_fields_when_set() -> None:
    payload = CheckResult(
        "caption_near_image",
        1,
        "fail",
        "Caption detached.",
        ["Line 7"],
        violation_type="caption_detachment",
        severity="major",
        confidence=0.85,
    ).to_dict()

    assert payload["violation_type"] == "caption_detachment"
    assert payload["severity"] == "major"
    assert payload["confidence"] == pytest.approx(0.85)


def test_builtin_issue_checks_emit_structured_violation_metadata(tmp_path: Path) -> None:
    image_issue_dir = tmp_path / "staging"
    image_issue_dir.mkdir()

    issue_results = [
        check_no_double_bullets("- • duplicated marker\n"),
        check_caption_near_image("*Figure 1. Detached caption.*\n\ntext\n"),
        check_images_locally_resolvable("![missing](images/nope.png)\n", image_issue_dir),
        check_paragraph_not_row_sliced(_row_sliced_markdown()),
    ]

    for result in issue_results:
        payload = result.to_dict()
        assert result.status in {"warn", "fail"}
        assert payload["violation_type"]
        assert payload["severity"] in {"minor", "major", "critical"}
        assert 0.0 <= payload["confidence"] <= 1.0


@pytest.mark.parametrize(
    "details",
    [
        pytest.param([], id="dependency_skip_warning"),
        pytest.param(["extension detail"], id="extension_name_collision"),
    ],
)
def test_builtin_named_result_without_explicit_metadata_stays_legacy_shaped(
    details: list[str],
) -> None:
    """Reusing a built-in check name never auto-injects metadata.

    Metadata is only ever set explicitly by the owning check, so a
    dependency-skip warning (no details) and a project extension that reuses a
    built-in name (with details) both keep the legacy serialized shape.
    """
    payload = CheckResult(
        "text_coverage",
        2,
        "warn",
        "Reused a built-in check name without explicit metadata.",
        details,
    ).to_dict()

    assert "violation_type" not in payload
    assert "severity" not in payload
    assert "confidence" not in payload


def test_text_coverage_issue_gets_explicit_violation_metadata() -> None:
    pytest.importorskip("fitz")
    result = check_text_coverage("", _probe_pdf_path(), sample_size=3)
    payload = result.to_dict()

    assert result.status in {"warn", "fail"}
    assert payload["violation_type"] == "missing_content"
    assert payload["severity"] in {"minor", "major"}
    assert payload["confidence"] == pytest.approx(0.80)


def test_structured_violation_metadata_does_not_change_scoring() -> None:
    plain = CheckResult(
        "custom_check",
        1,
        "fail",
        "Custom issue.",
        ["issue"],
    )
    structured = CheckResult(
        "custom_check",
        1,
        "fail",
        "Custom issue.",
        ["issue"],
        violation_type="formatting_only_minor",
        severity="minor",
        confidence=0.95,
    )

    assert score_check(structured) == pytest.approx(score_check(plain))


def _row_sliced_markdown() -> str:
    return "\n\n".join(
        [
            "The inspection team arrived at the north intake",
            "after the first alarm and found that the overflow",
            "had reached the lower service path before the",
            "operators could isolate the bypass valve",
            "because the level sensor was reporting stale",
            "values from the previous calibration window.",
            "They logged the incident and notified the duty",
            "engineer before clearing the temporary barrier.",
        ]
    )


def _probe_pdf_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "anydoc2md"
        / "probe_assets"
        / "probe_source_reference.pdf"
    )
