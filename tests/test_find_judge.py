from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz

from anydoc2md.judge_probe_case import build_probe_case
from anydoc2md.judge_probe_models import (
    ModelInfo,
    fetch_model_ids,
    parse_size_hint_billions,
)
from anydoc2md.judge_probe_checklist import ChecklistProbeVerdict
from anydoc2md.judge_probe_runner import probe_one_model
from anydoc2md.output_qa.runner import run_all


def test_parse_size_hint_billions_standard() -> None:
    assert parse_size_hint_billions("qwen2.5-7b-instruct") == 7.0
    assert parse_size_hint_billions("something-1.5b") == 1.5


def test_parse_size_hint_billions_prefers_active_hint() -> None:
    # MoE-style ids often include total + active; prefer active for "smallest" sorting.
    assert parse_size_hint_billions("qwen/qwen3.6-35b-a3b") == 3.0


def test_parse_size_hint_billions_moe_total() -> None:
    assert parse_size_hint_billions("mixtral-8x7b-instruct") == 56.0


def test_parse_size_hint_billions_none_when_missing() -> None:
    assert parse_size_hint_billions("no-size-here") is None


def test_render_progress_bar_is_stable() -> None:
    from anydoc2md.find_judge import (
        _color_status,
        _format_duration,
        _render_attempt_status,
        _render_progress,
    )

    assert "0/3" in _render_progress(0, 3, width=10)
    assert "1/3" in _render_progress(1, 3, width=10)
    assert "3/3" in _render_progress(3, 3, width=10)
    assert _render_progress(0, 0) == "[?] 0/0"
    assert _format_duration(61) == "01:01"
    assert _format_duration(3661) == "1:01:01"
    assert _color_status("PASS", enabled=False) == "PASS"
    assert "\033[32mPASS\033[0m" == _color_status("PASS", enabled=True)
    assert "\033[31mFAIL\033[0m" == _color_status("FAIL", enabled=True)
    attempt_status = _render_attempt_status(
        1,
        2,
        elapsed_s=18,
        eta_s=2876,
        status="FAIL",
        color_enabled=False,
    )
    assert "1/2 00:18/47:56 FAIL" in attempt_status


def test_select_models_filters_exact_names() -> None:
    from anydoc2md.find_judge import _select_models

    selected = _select_models(["a", "b", "c"], ["b", "c"])
    assert selected == ["b", "c"]


def test_select_models_rejects_missing_name() -> None:
    from anydoc2md.find_judge import _select_models

    try:
        _select_models(["a", "b"], ["c"])
    except ValueError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing model name")


def test_summarize_model_splits_load_and_answer_time() -> None:
    from anydoc2md.find_judge import _summarize_model
    from anydoc2md.judge_probe_runner import ProbeResult

    model = ModelInfo(model_id="test-7b", size_hint_b=7.0)
    summary = _summarize_model(
        model,
        [
            ProbeResult("test-7b", 7.0, 10.0, 100, "high", 4, True, "ok"),
            ProbeResult("test-7b", 7.0, 4.0, 100, "high", 4, True, "ok"),
            ProbeResult("test-7b", 7.0, 6.0, 100, "high", 4, True, "ok"),
        ],
    )

    assert summary.first_latency_s == 10.0
    assert summary.mean_answer_latency_s == 5.0
    assert summary.max_answer_latency_s == 6.0
    assert summary.estimated_load_overhead_s == 5.0
    assert summary.mean_latency_s == 20.0 / 3.0
    assert summary.answer_timeout_exceeded is False


def test_summarize_model_excludes_slow_steady_answer_time() -> None:
    from anydoc2md.find_judge import _summarize_model
    from anydoc2md.judge_probe_runner import ProbeResult

    model = ModelInfo(model_id="slow-7b", size_hint_b=7.0)
    summary = _summarize_model(
        model,
        [
            ProbeResult("slow-7b", 7.0, 90.0, 100, "high", 4, True, "ok"),
            ProbeResult("slow-7b", 7.0, 31.0, 100, "high", 4, True, "ok"),
            ProbeResult("slow-7b", 7.0, 29.0, 100, "high", 4, True, "ok"),
        ],
        answer_timeout_s=30.0,
    )

    assert summary.pass_count == 3
    assert summary.answer_timeout_exceeded is True
    assert summary.passed is False


def test_fetch_model_ids_parses_openai_shape() -> None:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "object": "list",
        "data": [{"id": "b"}, {"id": "a"}, {"id": "a"}, {"id": ""}, {}],
    }

    with patch("anydoc2md.judge_probe_models.requests.get", return_value=mock) as get:
        ids = fetch_model_ids("http://localhost:1234/v1")
        get.assert_called_once()

    assert ids == ["a", "b"]


def test_build_probe_case_writes_pdfs_and_markdown(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)
    assert case.source_pdf.exists()
    assert case.candidate_pdf.exists()
    # Ten-page, text-heavy fixture with embedded visual/table structure.
    assert case.traits.page_count >= 10
    assert case.traits.image_count >= 1
    assert case.traits.table_count >= 1
    assert case.traits.word_count >= 800
    assert case.traits.is_scanned is False
    candidate_doc = fitz.open(case.candidate_pdf)
    try:
        assert candidate_doc.page_count >= 10
    finally:
        candidate_doc.close()
    assert (case.candidate.staging_dir / "index.md").exists()
    assert (case.candidate.staging_dir / "images" / "probe_red_square.png").exists()


def test_probe_case_triggers_programmatic_qa_issue_coverage(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)
    report = run_all(case.candidate.staging_dir, case.source_pdf)
    non_pass = {check.name for check in report.checks if check.status != "pass"}

    assert {
        "no_double_bullets",
        "numbered_list_sequential",
        "heading_not_fragmented",
        "caption_near_image",
        "box_title_precedes_content",
        "image_size_plausible",
        "no_repeated_headings",
        "images_locally_resolvable",
        "image_count_match",
        "text_coverage",
    }.issubset(non_pass)


def test_probe_one_model_marks_pass_for_checklist_issues(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    verdict = ChecklistProbeVerdict(
        issues={
            "fragmented_heading": True,
            "double_bullet_markers": True,
            "malformed_dot_bullets": True,
            "numbered_list_out_of_order": True,
            "box_heading_without_content": True,
            "repeated_page_heading": True,
            "detached_caption": True,
            "wrong_caption": True,
            "flattened_table": True,
            "implausible_image_size": True,
            "missing_image_reference": False,
            "image_count_mismatch": False,
            "missing_source_text": False,
            "ocr_gibberish": False,
            "wrong_language_translation": False,
            "math_formula_loss": False,
        },
        tokens_used=123,
    )

    with patch("anydoc2md.judge_probe_runner.run_checklist_probe", return_value=verdict):
        result = probe_one_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=10,
            probe_case=case,
        )

    assert result.passed is True


def test_probe_one_model_fails_when_checklist_detection_is_low(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    verdict = ChecklistProbeVerdict(
        issues={
            "fragmented_heading": False,
            "double_bullet_markers": False,
            "malformed_dot_bullets": False,
            "numbered_list_out_of_order": False,
            "box_heading_without_content": False,
            "repeated_page_heading": False,
            "detached_caption": False,
            "wrong_caption": False,
            "flattened_table": True,
            "implausible_image_size": False,
            "missing_image_reference": False,
            "image_count_mismatch": False,
            "missing_source_text": False,
            "ocr_gibberish": False,
            "wrong_language_translation": False,
            "math_formula_loss": False,
        },
        tokens_used=123,
    )

    with patch("anydoc2md.judge_probe_runner.run_checklist_probe", return_value=verdict):
        result = probe_one_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=10,
            probe_case=case,
        )

    assert result.passed is False
    assert "checklist detected 1/13 expected issues" in result.reason


def test_probe_one_model_fails_on_checklist_false_positive(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    verdict = ChecklistProbeVerdict(
        issues={
            "fragmented_heading": True,
            "double_bullet_markers": True,
            "malformed_dot_bullets": True,
            "numbered_list_out_of_order": True,
            "box_heading_without_content": True,
            "repeated_page_heading": True,
            "detached_caption": True,
            "wrong_caption": True,
            "flattened_table": True,
            "implausible_image_size": True,
            "missing_image_reference": True,
            "image_count_mismatch": True,
            "missing_source_text": True,
            "ocr_gibberish": True,
            "wrong_language_translation": False,
            "math_formula_loss": False,
        },
        tokens_used=123,
    )

    with patch("anydoc2md.judge_probe_runner.run_checklist_probe", return_value=verdict):
        result = probe_one_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=10,
            probe_case=case,
        )

    assert result.passed is False
    assert result.reason == "false positives on control issues: ocr_gibberish"


def test_checklist_response_parser_accepts_fenced_json_strings() -> None:
    from anydoc2md.judge_probe_checklist import _parse_checklist_response

    raw = """```json
{
  "issues": {
    "fragmented_heading": "true",
    "double_bullet_markers": true,
    "ocr_gibberish": "false"
  },
  "confidence": "high"
}
```"""

    verdict = _parse_checklist_response(raw, tokens_used=42)

    assert verdict.succeeded is True
    assert verdict.tokens_used == 42
    assert verdict.issues["fragmented_heading"] is True
    assert verdict.issues["double_bullet_markers"] is True
    assert verdict.issues["ocr_gibberish"] is False


def test_checklist_response_parser_ignores_trailing_text() -> None:
    from anydoc2md.judge_probe_checklist import _parse_checklist_response

    raw = '{"issues": {"fragmented_heading": true}, "confidence": "high"}\nextra text'

    verdict = _parse_checklist_response(raw, tokens_used=2)

    assert verdict.succeeded is True
    assert verdict.issues["fragmented_heading"] is True


def test_checklist_response_parser_rejects_missing_issues_object() -> None:
    from anydoc2md.judge_probe_checklist import _parse_checklist_response

    verdict = _parse_checklist_response('{"confidence": "high"}', tokens_used=1)

    assert verdict.succeeded is False
    assert "missing object field" in verdict.error
