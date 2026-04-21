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
    from anydoc2md.find_judge import _render_progress

    assert "0/3" in _render_progress(0, 3, width=10)
    assert "1/3" in _render_progress(1, 3, width=10)
    assert "3/3" in _render_progress(3, 3, width=10)
    assert _render_progress(0, 0) == "[?] 0/0"


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

    def fake_probe_one_model(**kwargs):
        model = kwargs["model"]
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
            ]
        )
    assert rc == 0

    out = capsys.readouterr().out
    assert "Artifacts kept at:" in out

    match = re.search(r"Artifacts kept at: (.+)", out)
    assert match is not None
    artifacts_dir = Path(match.group(1).strip())
    assert artifacts_dir.exists()
    assert (artifacts_dir / "source.pdf").exists()
    assert (artifacts_dir / "candidate.pdf").exists()
