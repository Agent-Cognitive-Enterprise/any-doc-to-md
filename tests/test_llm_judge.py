"""
Core contract tests for anydoc2md.llm_judge result types.
"""
from __future__ import annotations

from anydoc2md.llm_judge import JudgeVerdict, JudgeViolation


class TestJudgeVerdict:
    def test_succeeded_true_when_not_error(self) -> None:
        verdict = JudgeVerdict(
            preferred_adapter="inhouse",
            confidence="high",
            reasoning="Good",
            notes={},
            model_used="m",
            tokens_used=100,
        )
        assert verdict.succeeded is True

    def test_succeeded_false_on_error(self) -> None:
        verdict = JudgeVerdict(
            preferred_adapter="",
            confidence="error",
            reasoning="",
            notes={},
            model_used="m",
            tokens_used=0,
            error="network failure",
        )
        assert verdict.succeeded is False

    def test_to_dict_has_all_keys(self) -> None:
        verdict = JudgeVerdict(
            preferred_adapter="a",
            confidence="medium",
            reasoning="ok",
            notes={"a": "note"},
            model_used="m",
            tokens_used=10,
        )
        result = verdict.to_dict()
        for key in (
            "preferred_adapter",
            "confidence",
            "reasoning",
            "notes",
            "model_used",
            "tokens_used",
            "input_tokens",
            "output_tokens",
            "violations",
            "window_verdicts",
            "overall_confidence",
            "uncertainty_note",
            "error",
        ):
            assert key in result


class TestJudgeViolation:
    def test_to_dict_round_trips_fields(self) -> None:
        violation = JudgeViolation(
            type="reading_order",
            severity="major",
            count=2,
            pages=[3, 4],
            confidence=0.91,
            evidence="caption before paragraph",
            root_cause="multicolumn merge",
        )
        assert violation.to_dict()["type"] == "reading_order"
