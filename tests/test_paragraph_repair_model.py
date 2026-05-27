from __future__ import annotations

import json

from anydoc2md.paragraph_repair.model import (
    ParagraphRepairReport,
    ParagraphRepairResult,
    ParagraphRepairSettings,
    bound_examples,
)


def test_default_settings_are_conservative() -> None:
    settings = ParagraphRepairSettings()

    assert settings.enabled is True
    assert settings.min_paragraphs == 20
    assert settings.min_short_ratio == 0.55
    assert settings.min_no_terminal_ratio == 0.35
    assert settings.min_continuation_ratio == 0.35
    assert settings.min_quality_delta == 0.75
    assert settings.max_merged_paragraph_chars == 2500
    assert settings.max_examples == 5
    assert settings.max_example_chars == 160


def test_report_to_dict_is_json_friendly() -> None:
    report = ParagraphRepairReport(
        attempted=True,
        accepted=False,
        reason="quality_delta_too_small",
        original_paragraph_count=24,
        repaired_paragraph_count=12,
        merge_group_count=3,
        before_score=4.25,
        after_score=3.9,
        signals={
            "short_ratio": 0.72,
            "run_count": 2,
            "dominant_reason": "continuation_pairs",
            "content_preserved": True,
        },
        examples=["Line 4 -> Line 5"],
    )

    payload = report.to_dict()

    assert payload == {
        "attempted": True,
        "accepted": False,
        "reason": "quality_delta_too_small",
        "original_paragraph_count": 24,
        "repaired_paragraph_count": 12,
        "merge_group_count": 3,
        "before_score": 4.25,
        "after_score": 3.9,
        "signals": {
            "short_ratio": 0.72,
            "run_count": 2,
            "dominant_reason": "continuation_pairs",
            "content_preserved": True,
        },
        "examples": ["Line 4 -> Line 5"],
    }
    json.dumps(payload)


def test_report_bounds_examples_on_construction() -> None:
    long_example = "x" * (ParagraphRepairSettings().max_example_chars + 50)
    report = ParagraphRepairReport(
        attempted=True,
        accepted=True,
        reason="accepted",
        original_paragraph_count=40,
        repaired_paragraph_count=10,
        merge_group_count=5,
        before_score=10.0,
        after_score=3.0,
        examples=[long_example for _ in range(10)],
    )

    assert len(report.examples) == ParagraphRepairSettings().max_examples
    assert all(
        len(example) <= ParagraphRepairSettings().max_example_chars
        for example in report.examples
    )
    assert report.to_dict()["examples"] == report.examples


def test_report_honors_tighter_run_settings() -> None:
    settings = ParagraphRepairSettings(max_examples=1, max_example_chars=5)
    report = ParagraphRepairReport(
        attempted=True,
        accepted=True,
        reason="accepted",
        original_paragraph_count=40,
        repaired_paragraph_count=10,
        merge_group_count=5,
        before_score=10.0,
        after_score=3.0,
        examples=["y" * 200 for _ in range(3)],
        settings=settings,
    )

    assert len(report.examples) == 1
    assert all(len(example) <= 5 for example in report.examples)


def test_report_honors_looser_run_settings() -> None:
    settings = ParagraphRepairSettings(max_example_chars=300)
    long_example = "y" * 200

    report = ParagraphRepairReport(
        attempted=True,
        accepted=True,
        reason="accepted",
        original_paragraph_count=40,
        repaired_paragraph_count=10,
        merge_group_count=5,
        before_score=10.0,
        after_score=3.0,
        examples=[long_example],
        settings=settings,
    )

    # 200 chars exceeds the default 160 cap but is within the run-configured 300,
    # so it must be preserved in full rather than silently clobbered to defaults.
    assert report.examples == [long_example]


def test_report_settings_excluded_from_serialization_and_equality() -> None:
    kwargs = dict(
        attempted=True,
        accepted=True,
        reason="accepted",
        original_paragraph_count=21,
        repaired_paragraph_count=4,
        merge_group_count=4,
        before_score=8.0,
        after_score=2.0,
        examples=["short"],
    )
    default_report = ParagraphRepairReport(**kwargs)
    configured_report = ParagraphRepairReport(
        **kwargs, settings=ParagraphRepairSettings(max_examples=1)
    )

    assert "settings" not in default_report.to_dict()
    assert default_report == configured_report
    assert "settings" not in repr(default_report)


def test_result_to_dict_is_json_friendly() -> None:
    report = ParagraphRepairReport(
        attempted=True,
        accepted=True,
        reason="accepted",
        original_paragraph_count=21,
        repaired_paragraph_count=4,
        merge_group_count=4,
        before_score=8.0,
        after_score=2.0,
    )
    result = ParagraphRepairResult(text="Repaired Markdown", report=report)

    payload = result.to_dict()

    assert payload["text"] == "Repaired Markdown"
    assert payload["report"]["accepted"] is True
    json.dumps(payload)


def test_bound_examples_limits_count_and_length() -> None:
    settings = ParagraphRepairSettings(max_examples=2, max_example_chars=12)
    examples = [
        "short",
        "this example is intentionally too long",
        "ignored because count is bounded",
    ]

    bounded = bound_examples(examples, settings)

    assert bounded == ["short", "this exam..."]


def test_bound_examples_strips_truncation_boundary_whitespace() -> None:
    settings = ParagraphRepairSettings(max_examples=1, max_example_chars=12)

    bounded = bound_examples(["word      extra"], settings)

    assert bounded == ["word..."]
    assert len(bounded[0]) <= settings.max_example_chars


def test_bound_examples_respects_degenerate_character_caps() -> None:
    examples = ["abcdef"]

    assert bound_examples(examples, ParagraphRepairSettings(max_example_chars=0)) == [""]
    assert bound_examples(examples, ParagraphRepairSettings(max_example_chars=1)) == ["."]
    assert bound_examples(examples, ParagraphRepairSettings(max_example_chars=2)) == [".."]


def test_bound_examples_uses_default_settings() -> None:
    examples = [f"example {i}" for i in range(10)]

    bounded = bound_examples(examples)

    assert len(bounded) == ParagraphRepairSettings().max_examples
    assert all(
        len(example) <= ParagraphRepairSettings().max_example_chars
        for example in bounded
    )
