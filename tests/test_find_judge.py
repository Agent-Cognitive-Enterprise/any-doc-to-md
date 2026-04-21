from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from anydoc2md.judge_probe_case import build_probe_case
from anydoc2md.judge_probe_models import (
    ModelInfo,
    fetch_model_ids,
    parse_size_hint_billions,
)
from anydoc2md.judge_probe_runner import probe_one_model
from anydoc2md.llm_judge import JudgeVerdict, JudgeViolation


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
    # Two-page PDF with at least one embedded image.
    assert case.traits.page_count == 2
    assert case.traits.image_count >= 1
    assert (case.candidate.staging_dir / "index.md").exists()


def test_probe_one_model_marks_pass_when_markers_present(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    violations = [
        JudgeViolation(
            type="reading_order",
            severity="major",
            evidence=" ".join(
                [
                    "Steps are out of order; before/after timing mismatch; figure caption wrong.",
                    "INTRO_MARKER_7F3A",
                    "STEP_ONE_MARKER_9A1C",
                    "STEP_TWO_MARKER_B52D",
                    "FIGURE_MARKER_C1D0",
                ]
            ),
        ),
        JudgeViolation(
            type="caption_mismatch",
            severity="major",
            evidence="FIGURE_MARKER_C1D0",
        ),
    ]
    verdict = JudgeVerdict(
        preferred_adapter="synthetic",
        confidence="high",
        reasoning="Found issues.",
        notes={"synthetic": "bad"},
        model_used="m",
        tokens_used=123,
        violations=violations,
    )

    with patch("anydoc2md.judge_probe_runner.judge_candidate_against_source", return_value=verdict):
        result = probe_one_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=10,
            probe_case=case,
        )

    assert result.passed is True
