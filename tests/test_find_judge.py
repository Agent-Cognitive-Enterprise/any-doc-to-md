from __future__ import annotations

from pathlib import Path
import re
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


def test_render_progress_bar_is_stable() -> None:
    from anydoc2md.find_judge import _color_status, _format_duration, _render_progress

    assert "0/3" in _render_progress(0, 3, width=10)
    assert "1/3" in _render_progress(1, 3, width=10)
    assert "3/3" in _render_progress(3, 3, width=10)
    assert _render_progress(0, 0) == "[?] 0/0"
    assert _format_duration(61) == "01:01"
    assert _format_duration(3661) == "1:01:01"
    assert _color_status("PASS", enabled=False) == "PASS"
    assert "\033[32mPASS\033[0m" == _color_status("PASS", enabled=True)
    assert "\033[31mFAIL\033[0m" == _color_status("FAIL", enabled=True)


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
    # Two-page PDF with at least one embedded image.
    assert case.traits.page_count == 2
    assert case.traits.image_count >= 1
    assert case.traits.is_scanned is False
    assert (case.candidate.staging_dir / "index.md").exists()
    assert (case.candidate.staging_dir / "images" / "probe_red_square.png").exists()


def test_probe_one_model_marks_pass_for_semantic_issue_classes(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    violations = [
        JudgeViolation(
            type="heading_fragmentation",
            severity="major",
            evidence="The title and heading formatting are split and malformed.",
        ),
        JudgeViolation(
            type="list_formatting",
            severity="major",
            evidence="Bullet list markers are degraded and the numbering sequence is out of order.",
        ),
        JudgeViolation(
            type="table_flattening",
            severity="major",
            evidence="The table is flattened into plain lines and the figure caption points to the wrong step.",
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


def test_probe_one_model_fails_when_only_one_issue_class_is_found(tmp_path: Path) -> None:
    case = build_probe_case(tmp_path)

    verdict = JudgeVerdict(
        preferred_adapter="synthetic",
        confidence="high",
        reasoning="The table is flattened.",
        notes={"synthetic": "table problem"},
        model_used="m",
        tokens_used=123,
        violations=[
            JudgeViolation(
                type="table_flattening",
                severity="major",
                evidence="The table is flattened.",
            ),
            JudgeViolation(
                type="table_flattening",
                severity="major",
                evidence="Rows and columns are lost.",
            ),
        ],
    )

    with patch("anydoc2md.judge_probe_runner.judge_candidate_against_source", return_value=verdict):
        result = probe_one_model(
            model=ModelInfo(model_id="test-7b", size_hint_b=7.0),
            judge_url="http://localhost:1234/v1",
            judge_timeout_s=10,
            probe_case=case,
        )

    assert result.passed is False
    assert "surfaced 1/5 issue classes" in result.reason


def test_main_keep_artifacts_writes_probe_pdfs(tmp_path: Path, capsys) -> None:
    from anydoc2md.find_judge import main
    from anydoc2md.judge_probe_runner import ProbeResult

    seen_models: list[str] = []

    def fake_probe_one_model(**kwargs):
        model = kwargs["model"]
        seen_models.append(model.model_id)
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=0.01,
            tokens_used=10,
            confidence="high",
            violations_count=3,
            passed=True,
            reason="ok",
        )

    with (
        patch("anydoc2md.find_judge.fetch_model_ids", return_value=["test-7b"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
    ):
        rc = main(
            [
                "--judge-url",
                "http://localhost:1234/v1",
                "--artifacts-dir",
                str(tmp_path),
                "--repeats",
                "1",
            ]
        )
    assert rc == 0
    assert seen_models == ["test-7b"]

    out = capsys.readouterr().out
    assert "Artifacts kept at:" in out

    match = re.search(r"Artifacts kept at: (.+)", out)
    assert match is not None
    artifacts_dir = Path(match.group(1).strip())
    assert artifacts_dir.exists()
    assert (artifacts_dir / "source.pdf").exists()
    assert (artifacts_dir / "candidate.pdf").exists()


def test_main_repeats_and_model_filter(tmp_path: Path, capsys) -> None:
    from anydoc2md.find_judge import main
    from anydoc2md.judge_probe_runner import ProbeResult

    seen_models: list[str] = []

    def fake_probe_one_model(**kwargs):
        model = kwargs["model"]
        seen_models.append(model.model_id)
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=0.02,
            tokens_used=20,
            confidence="high",
            violations_count=4,
            passed=True,
            reason="ok",
        )

    with (
        patch("anydoc2md.find_judge.fetch_model_ids", return_value=["a", "focus", "z"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
    ):
        rc = main(
            [
                "--judge-url",
                "http://localhost:1234/v1",
                "--model-name",
                "focus",
                "--repeats",
                "3",
                "--artifacts-dir",
                str(tmp_path),
            ]
        )

    assert rc == 0
    assert seen_models == ["focus", "focus", "focus"]
    out = capsys.readouterr().out
    assert "Models selected: 1" in out
    assert "Repeats per model: 3" in out
    assert "Elapsed time:" in out
    assert "answer_mean=" in out
    assert "answer_max=" in out
    assert "load_est=" in out
