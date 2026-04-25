"""
Structured response parsing tests for anydoc2md.llm_judge.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests._llm_judge_helpers import adapter_result

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.llm_judge import _parse_verdict, _parse_violations


class TestParseVerdict:
    def _candidates(self, tmp_path: Path) -> list[AdapterResult]:
        return [
            adapter_result("alpha", tmp_path, "# Alpha"),
            adapter_result("beta", tmp_path, "# Beta"),
        ]

    def test_happy_path(self, tmp_path: Path) -> None:
        raw = json.dumps(
            {
                "preferred": "alpha",
                "confidence": "high",
                "reasoning": "Alpha is better.",
                "notes": {"alpha": "good", "beta": "acceptable"},
            }
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 100)
        assert verdict.preferred_adapter == "alpha"
        assert verdict.confidence == "high"
        assert verdict.succeeded is True

    def test_strips_code_fences(self, tmp_path: Path) -> None:
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "preferred": "beta",
                    "confidence": "medium",
                    "reasoning": "ok",
                    "notes": {},
                }
            )
            + "\n```"
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.preferred_adapter == "beta"

    def test_recovers_first_json_object_when_trailing_text_present(
        self,
        tmp_path: Path,
    ) -> None:
        raw = (
            json.dumps(
                {
                    "preferred": "alpha",
                    "confidence": "high",
                    "reasoning": "ok",
                    "notes": {},
                }
            )
            + "\nextra trailing text"
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.preferred_adapter == "alpha"

    def test_recovers_when_control_characters_break_json(self, tmp_path: Path) -> None:
        raw = (
            "{\n"
            '  "preferred": "alpha",\n'
            '  "confidence": "low",\n'
            '  "reasoning": "bad\x08text",\n'
            '  "notes": {}\n'
            "}"
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.preferred_adapter == "alpha"

    def test_recovers_when_literal_newline_breaks_json_string(
        self,
        tmp_path: Path,
    ) -> None:
        raw = (
            "{\n"
            '  "preferred": "alpha",\n'
            '  "confidence": "medium",\n'
            '  "reasoning": "line one\nline two",\n'
            '  "notes": {}\n'
            "}"
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.preferred_adapter == "alpha"
        assert "line one" in verdict.reasoning

    def test_recovers_when_json_tail_is_truncated(self, tmp_path: Path) -> None:
        raw = (
            "{\n"
            '  "preferred": "alpha",\n'
            '  "confidence": "low",\n'
            '  "reasoning": "semantic mismatch detected'
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.preferred_adapter == "alpha"
        assert verdict.confidence == "low"
        assert "semantic mismatch detected" in verdict.reasoning

    def test_unknown_adapter_returns_error(self, tmp_path: Path) -> None:
        raw = json.dumps(
            {
                "preferred": "nonexistent",
                "confidence": "high",
                "reasoning": "ok",
                "notes": {},
            }
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.confidence == "error"
        assert "nonexistent" in verdict.error

    def test_malformed_json_returns_error(self, tmp_path: Path) -> None:
        verdict = _parse_verdict("{bad json", self._candidates(tmp_path), "model", 0)
        assert verdict.confidence == "error"
        assert "JSON" in verdict.error

    def test_invalid_confidence_defaults_to_medium(self, tmp_path: Path) -> None:
        raw = json.dumps(
            {
                "preferred": "alpha",
                "confidence": "very_high",
                "reasoning": "ok",
                "notes": {},
            }
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert verdict.confidence == "medium"

    def test_tokens_stored(self, tmp_path: Path) -> None:
        raw = json.dumps(
            {
                "preferred": "alpha",
                "confidence": "low",
                "reasoning": "ok",
                "notes": {},
            }
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 999)
        assert verdict.tokens_used == 999

    def test_parses_structured_violations(self, tmp_path: Path) -> None:
        raw = json.dumps(
            {
                "preferred": "alpha",
                "confidence": "high",
                "reasoning": "alpha wins",
                "notes": {},
                "violations": [
                    {
                        "type": "caption_detachment",
                        "severity": "major",
                        "count": 2,
                        "pages": [3],
                        "confidence": 0.9,
                        "evidence": "caption separated from image",
                        "root_cause": "image ordering",
                    }
                ],
                "overall_confidence": 0.88,
                "uncertainty_note": "check page 3",
            }
        )
        verdict = _parse_verdict(raw, self._candidates(tmp_path), "model", 5)
        assert len(verdict.violations) == 1
        assert verdict.violations[0].type == "caption_detachment"
        assert verdict.overall_confidence == 0.88
        assert verdict.uncertainty_note == "check page 3"


class TestParseViolations:
    def test_ignores_non_dict_items(self) -> None:
        violations = _parse_violations(
            ["bad", {"type": "reading_order", "severity": "major"}]
        )
        assert len(violations) == 1
        assert violations[0].type == "reading_order"
