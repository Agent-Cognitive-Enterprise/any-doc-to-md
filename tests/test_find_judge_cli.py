from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import patch

from anydoc2md.judge_probe_runner import ProbeResult


def test_main_keep_artifacts_writes_probe_pdfs(tmp_path: Path, capsys) -> None:
    from anydoc2md.find_judge import main

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
                "10",
                "--artifacts-dir",
                str(tmp_path),
            ]
        )

    assert rc == 0
    assert seen_models == ["focus"] * 10
    out = capsys.readouterr().out
    assert "Models selected: 1" in out
    assert "Repeats per model: 10" in out
    assert "Probe issue gate: find at least 10/13 expected issue classes" in out
    assert "Pass criteria: 10/10 repeats pass with no steady answer above 30s." in out
    assert "Elapsed time:" in out
    assert "answer_mean=" in out
    assert "answer_max=" in out
    assert "load_est=" in out
    assert "MODEL PASS focus | pass=10/10" in out
    assert out.rfind("MODEL PASS focus") > out.rfind("repeat 10/10")


def test_main_stop_on_fail_is_default_and_continues_to_next_model(
    tmp_path: Path,
    capsys,
) -> None:
    from anydoc2md.find_judge import main

    seen_models: list[str] = []

    def fake_probe_one_model(**kwargs):
        model = kwargs["model"]
        seen_models.append(model.model_id)
        if model.model_id == "bad":
            return ProbeResult(
                model_id=model.model_id,
                size_hint_b=model.size_hint_b,
                latency_s=0.02,
                tokens_used=20,
                confidence="high",
                violations_count=1,
                passed=False,
                reason="low detection rate: 1 violations reported; need at least 2",
            )
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
        patch("anydoc2md.find_judge.fetch_model_ids", return_value=["bad", "good"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
    ):
        rc = main(
            [
                "--judge-url",
                "http://localhost:1234/v1",
                "--repeats",
                "10",
                "--artifacts-dir",
                str(tmp_path),
                "--show-all",
            ]
        )

    assert rc == 0
    assert seen_models == ["bad"] + ["good"] * 10
    out = capsys.readouterr().out
    assert "Stop on first fail: yes" in out
    assert "Stopping bad after first failed repeat (1/10)" in out
    assert "MODEL FAIL bad | pass=0/1" in out
    assert "MODEL PASS good | pass=10/10" in out
    assert "low detection rate" not in out


def test_main_no_stop_on_fail_runs_all_repeats(tmp_path: Path, capsys) -> None:
    from anydoc2md.find_judge import main

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
            violations_count=1,
            passed=False,
            reason="low detection rate: 1 violations reported; need at least 2",
        )

    with (
        patch("anydoc2md.find_judge.fetch_model_ids", return_value=["bad"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
    ):
        rc = main(
            [
                "--judge-url",
                "http://localhost:1234/v1",
                "--repeats",
                "3",
                "--artifacts-dir",
                str(tmp_path),
                "--show-all",
                "--no-stop-on-fail",
            ]
        )

    assert rc == 1
    assert seen_models == ["bad"] * 3
    out = capsys.readouterr().out
    assert "Stop on first fail: no" in out
    assert "Stopping bad after first failed repeat" not in out
    assert "MODEL FAIL bad | pass=0/3" in out
    assert "low detection rate" not in out


def test_main_show_errors_prints_failure_reasons(tmp_path: Path, capsys) -> None:
    from anydoc2md.find_judge import main

    def fake_probe_one_model(**kwargs):
        model = kwargs["model"]
        return ProbeResult(
            model_id=model.model_id,
            size_hint_b=model.size_hint_b,
            latency_s=0.02,
            tokens_used=20,
            confidence="high",
            violations_count=1,
            passed=False,
            reason="low detection rate: 1 violations reported; need at least 2",
        )

    with (
        patch("anydoc2md.find_judge.fetch_model_ids", return_value=["bad"]),
        patch("anydoc2md.find_judge.probe_one_model", side_effect=fake_probe_one_model),
    ):
        rc = main(
            [
                "--judge-url",
                "http://localhost:1234/v1",
                "--repeats",
                "3",
                "--artifacts-dir",
                str(tmp_path),
                "--show-all",
                "--show-errors",
            ]
        )

    assert rc == 1
    out = capsys.readouterr().out
    assert "Show diagnostic errors: yes" in out
    assert "MODEL FAIL bad | pass=0/1" in out
    assert "FAIL bad | size=? | first_load+answer=" in out
    assert "low detection rate: 1 violations reported; need at least 2" in out
