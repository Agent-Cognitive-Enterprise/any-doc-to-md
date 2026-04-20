"""
Tests for anydoc2md.llm_judge.

All LLM calls are mocked — tests run without a live LM Studio instance.
Covers:
  - JudgeVerdict contract (succeeded, to_dict)
  - _excerpt: front/mid/end sampling, short text passthrough
  - _evidence_block: contains adapter name, stats, excerpt
  - _traits_summary: reflects DocumentTraits fields
  - build_prompt: returns (system, user), system has JSON schema, user has evidence
  - _parse_verdict: happy path, unknown adapter, malformed JSON, code-fence stripping
  - judge_near_tie: single candidate shortcut, mocked happy path, mocked failure
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import (
    DocumentTraits,
    _unknown_traits,
)
from anydoc2md.llm_judge import (
    JudgeVerdict,
    JudgeViolation,
    _evidence_block,
    _excerpt,
    _parse_verdict,
    _parse_violations,
    _traits_summary,
    build_prompt,
    judge_near_tie,
    EXCERPT_CHARS_PER_ADAPTER,
)
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _adapter_result(name: str, staging_dir: Path, md: str) -> AdapterResult:
    staging = staging_dir / name
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "index.md").write_text(md, encoding="utf-8")
    return AdapterResult(
        method_name=name,
        method_version="1",
        command_invoked="",
        exit_code=0,
        staging_dir=staging,
        timing_ms=10,
        status="ok",
    )


def _traits(**kwargs) -> DocumentTraits:
    defaults = dict(
        file_type="pdf", page_count=5, image_count=2, table_count=1,
        word_count=500, is_scanned=False, is_image_heavy=False,
        is_table_heavy=False, is_multi_column=False,
        is_text_only=False, has_math=False,
    )
    defaults.update(kwargs)
    return DocumentTraits(**defaults)


def _mock_response(preferred: str, confidence: str = "high", reasoning: str = "Good.") -> MagicMock:
    """Build a mock requests.Response for a successful LM Studio call."""
    body = json.dumps({
        "choices": [{
            "message": {
                "content": json.dumps({
                    "preferred": preferred,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "notes": {preferred: "Best output."},
                    "violations": [{
                        "type": "reading_order",
                        "severity": "major",
                        "count": 1,
                        "pages": [2],
                        "confidence": 0.91,
                        "evidence": "Paragraphs are out of order.",
                        "root_cause": "multicolumn merge",
                    }],
                    "overall_confidence": 0.87,
                    "uncertainty_note": "",
                })
            }
        }],
        "usage": {"total_tokens": 512},
    })
    mock = MagicMock()
    mock.json.return_value = json.loads(body)
    mock.raise_for_status = MagicMock()
    return mock


def _judge_settings(
    url: str = "http://localhost:1234/v1",
    model: str = "qwen/qwen3.6-35b-a3b",
) -> JudgeSettings:
    return JudgeSettings(url=url, model=model)


# =========================================================================== #
# JudgeVerdict contract
# =========================================================================== #

class TestJudgeVerdict:
    def test_succeeded_true_when_not_error(self) -> None:
        v = JudgeVerdict(
            preferred_adapter="inhouse", confidence="high",
            reasoning="Good", notes={}, model_used="m", tokens_used=100,
        )
        assert v.succeeded is True

    def test_succeeded_false_on_error(self) -> None:
        v = JudgeVerdict(
            preferred_adapter="", confidence="error",
            reasoning="", notes={}, model_used="m", tokens_used=0,
            error="network failure",
        )
        assert v.succeeded is False

    def test_to_dict_has_all_keys(self) -> None:
        v = JudgeVerdict(
            preferred_adapter="a", confidence="medium", reasoning="ok",
            notes={"a": "note"}, model_used="m", tokens_used=10,
        )
        d = v.to_dict()
        for k in ("preferred_adapter", "confidence", "reasoning", "notes",
                  "model_used", "tokens_used", "violations",
                  "overall_confidence", "uncertainty_note", "error"):
            assert k in d


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


# =========================================================================== #
# _excerpt
# =========================================================================== #

class TestExcerpt:
    def test_short_text_returned_unchanged(self) -> None:
        text = "Hello world"
        assert _excerpt(text) == text

    def test_at_limit_returned_unchanged(self) -> None:
        text = "x" * EXCERPT_CHARS_PER_ADAPTER
        assert _excerpt(text) == text

    def test_long_text_truncated_to_within_budget(self) -> None:
        text = "A" * 20_000
        result = _excerpt(text)
        # Allow some overhead for labels ("...middle..." etc.)
        assert len(result) <= EXCERPT_CHARS_PER_ADAPTER + 200

    def test_long_text_contains_front(self) -> None:
        text = "START_MARKER" + "x" * 10_000 + "END_MARKER"
        result = _excerpt(text)
        assert "START_MARKER" in result

    def test_long_text_contains_end(self) -> None:
        text = "x" * 10_000 + "END_MARKER"
        result = _excerpt(text)
        assert "END_MARKER" in result

    def test_long_text_contains_middle_label(self) -> None:
        text = "x" * 10_000
        result = _excerpt(text)
        assert "middle" in result.lower()


# =========================================================================== #
# _evidence_block
# =========================================================================== #

class TestEvidenceBlock:
    def test_contains_adapter_name(self, tmp_path: Path) -> None:
        r = _adapter_result("docling", tmp_path, "# Title\n\nSome text.")
        block = _evidence_block(r)
        assert "docling" in block

    def test_contains_stats(self, tmp_path: Path) -> None:
        r = _adapter_result("inhouse", tmp_path, "# H\n\nWord " * 50)
        block = _evidence_block(r)
        assert "chars" in block
        assert "words" in block

    def test_contains_markdown_fence(self, tmp_path: Path) -> None:
        r = _adapter_result("markitdown", tmp_path, "# Hello")
        block = _evidence_block(r)
        assert "```markdown" in block

    def test_image_count_in_stats(self, tmp_path: Path) -> None:
        md = '<img src="images/a.png" alt="x" width="10" height="10">\n# Title\n'
        r = _adapter_result("docling", tmp_path, md)
        block = _evidence_block(r)
        assert "1 image" in block


# =========================================================================== #
# _traits_summary
# =========================================================================== #

class TestTraitsSummary:
    def test_scanned_flagged(self) -> None:
        t = _traits(is_scanned=True)
        assert "scanned" in _traits_summary(t).lower()

    def test_image_heavy_flagged(self) -> None:
        t = _traits(is_image_heavy=True)
        assert "image" in _traits_summary(t).lower()

    def test_table_heavy_flagged(self) -> None:
        t = _traits(is_table_heavy=True)
        assert "table" in _traits_summary(t).lower()

    def test_standard_doc_label_when_no_flags(self) -> None:
        t = _traits()
        assert "standard" in _traits_summary(t).lower()

    def test_file_type_present(self) -> None:
        t = _traits(file_type="pdf")
        assert "PDF" in _traits_summary(t)


# =========================================================================== #
# build_prompt
# =========================================================================== #

class TestBuildPrompt:
    def test_returns_two_strings(self, tmp_path: Path) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        system, user = build_prompt([a, b], _traits())
        assert isinstance(system, str) and isinstance(user, str)

    def test_system_contains_json_schema(self, tmp_path: Path) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        system, _ = build_prompt([a, b], _traits())
        assert '"preferred"' in system
        assert '"confidence"' in system
        assert '"violations"' in system

    def test_user_contains_adapter_names(self, tmp_path: Path) -> None:
        a = _adapter_result("inhouse", tmp_path, "# In-house")
        b = _adapter_result("docling", tmp_path, "# Docling")
        _, user = build_prompt([a, b], _traits())
        assert "inhouse" in user
        assert "docling" in user

    def test_user_contains_traits_summary(self, tmp_path: Path) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        _, user = build_prompt([a, b], _traits(is_table_heavy=True))
        assert "table" in user.lower()


# =========================================================================== #
# _parse_verdict
# =========================================================================== #

class TestParseVerdict:
    def _candidates(self, tmp_path: Path) -> list[AdapterResult]:
        return [
            _adapter_result("alpha", tmp_path, "# Alpha"),
            _adapter_result("beta", tmp_path, "# Beta"),
        ]

    def test_happy_path(self, tmp_path: Path) -> None:
        raw = json.dumps({
            "preferred": "alpha",
            "confidence": "high",
            "reasoning": "Alpha is better.",
            "notes": {"alpha": "good", "beta": "acceptable"},
        })
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 100)
        assert v.preferred_adapter == "alpha"
        assert v.confidence == "high"
        assert v.succeeded is True

    def test_strips_code_fences(self, tmp_path: Path) -> None:
        raw = "```json\n" + json.dumps({"preferred": "beta", "confidence": "medium",
                                         "reasoning": "ok", "notes": {}}) + "\n```"
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert v.preferred_adapter == "beta"

    def test_unknown_adapter_returns_error(self, tmp_path: Path) -> None:
        raw = json.dumps({"preferred": "nonexistent", "confidence": "high",
                           "reasoning": "ok", "notes": {}})
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert v.confidence == "error"
        assert "nonexistent" in v.error

    def test_malformed_json_returns_error(self, tmp_path: Path) -> None:
        v = _parse_verdict("{bad json", self._candidates(tmp_path), "model", 0)
        assert v.confidence == "error"
        assert "JSON" in v.error

    def test_invalid_confidence_defaults_to_medium(self, tmp_path: Path) -> None:
        raw = json.dumps({"preferred": "alpha", "confidence": "very_high",
                           "reasoning": "ok", "notes": {}})
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 0)
        assert v.confidence == "medium"

    def test_tokens_stored(self, tmp_path: Path) -> None:
        raw = json.dumps({"preferred": "alpha", "confidence": "low",
                           "reasoning": "ok", "notes": {}})
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 999)
        assert v.tokens_used == 999

    def test_parses_structured_violations(self, tmp_path: Path) -> None:
        raw = json.dumps({
            "preferred": "alpha",
            "confidence": "high",
            "reasoning": "alpha wins",
            "notes": {},
            "violations": [{
                "type": "caption_detachment",
                "severity": "major",
                "count": 2,
                "pages": [3],
                "confidence": 0.9,
                "evidence": "caption separated from image",
                "root_cause": "image ordering",
            }],
            "overall_confidence": 0.88,
            "uncertainty_note": "check page 3",
        })
        v = _parse_verdict(raw, self._candidates(tmp_path), "model", 5)
        assert len(v.violations) == 1
        assert v.violations[0].type == "caption_detachment"
        assert v.overall_confidence == 0.88
        assert v.uncertainty_note == "check page 3"


class TestParseViolations:
    def test_ignores_non_dict_items(self) -> None:
        violations = _parse_violations(["bad", {"type": "reading_order", "severity": "major"}])
        assert len(violations) == 1
        assert violations[0].type == "reading_order"


# =========================================================================== #
# judge_near_tie
# =========================================================================== #

class TestJudgeNearTie:
    def test_single_candidate_shortcut(self, tmp_path: Path) -> None:
        a = _adapter_result("only", tmp_path, "# Only")
        v = judge_near_tie([a], Path("/src/doc.pdf"), _traits())
        assert v.preferred_adapter == "only"
        assert v.succeeded is True
        assert v.tokens_used == 0

    def test_empty_candidates_shortcut(self, tmp_path: Path) -> None:
        v = judge_near_tie([], Path("/src/doc.pdf"), _traits())
        assert v.preferred_adapter == ""

    def test_missing_env_returns_error_verdict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        monkeypatch.delenv("ANYDOC2MD_JUDGE_URL", raising=False)
        monkeypatch.delenv("ANYDOC2MD_JUDGE_MODEL", raising=False)

        v = judge_near_tie([a, b], Path("/src/doc.pdf"), _traits())

        assert v.confidence == "error"
        assert "Missing required anydoc2md judge env vars" in v.error

    def test_happy_path_mocked(self, tmp_path: Path) -> None:
        a = _adapter_result("inhouse", tmp_path, "# Inhouse\n\nGood text.")
        b = _adapter_result("docling", tmp_path, "# Docling\n\nAlso good.")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = _mock_response("inhouse")
            v = judge_near_tie(
                [a, b], Path("/src/doc.pdf"), _traits(),
                settings=_judge_settings(),
            )

        assert v.preferred_adapter == "inhouse"
        assert v.confidence == "high"
        assert v.succeeded is True
        assert v.tokens_used == 512
        assert v.violations[0].type == "reading_order"

    def test_network_failure_returns_error_verdict(self, tmp_path: Path) -> None:
        import requests as req
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.side_effect = Exception("Connection refused")
            v = judge_near_tie(
                [a, b], Path("/src/doc.pdf"), _traits(),
                settings=_judge_settings(),
            )

        assert v.confidence == "error"
        assert v.preferred_adapter == ""
        assert "Connection refused" in v.error

    def test_custom_model_passed_through(self, tmp_path: Path) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        settings = _judge_settings(model="qwen/qwen3-32b")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = _mock_response("a")
            v = judge_near_tie(
                [a, b], Path("/src/doc.pdf"), _traits(),
                settings=settings,
            )

        assert v.model_used == "qwen/qwen3-32b"
        call_kwargs = mock_req.post.call_args
        assert "qwen/qwen3-32b" in str(call_kwargs)

    def test_custom_url_passed_through(self, tmp_path: Path) -> None:
        a = _adapter_result("a", tmp_path, "# A")
        b = _adapter_result("b", tmp_path, "# B")
        settings = _judge_settings(url="http://localhost:9999/v1")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = _mock_response("a")
            judge_near_tie(
                [a, b], Path("/src/doc.pdf"), _traits(),
                settings=settings,
            )

        url_called = mock_req.post.call_args[0][0]
        assert "localhost:9999" in url_called


class TestJudgeSettings:
    def test_load_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MODEL", "qwen/test-model")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_TIMEOUT_S", "120")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MAX_TOKENS", "2048")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_DISABLE_THINKING", "false")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_TEMPERATURE", "0.2")

        settings = load_judge_settings_from_env()

        assert settings.url == "http://localhost:1234/v1"
        assert settings.model == "qwen/test-model"
        assert settings.timeout_s == 120
        assert settings.max_tokens == 2048
        assert settings.disable_thinking is False
        assert settings.temperature == 0.2

    def test_missing_required_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANYDOC2MD_JUDGE_URL", raising=False)
        monkeypatch.delenv("ANYDOC2MD_JUDGE_MODEL", raising=False)

        with pytest.raises(AnyDocToMdConfigError):
            load_judge_settings_from_env()

    def test_invalid_bool_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MODEL", "qwen/test-model")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_DISABLE_THINKING", "sometimes")

        with pytest.raises(AnyDocToMdConfigError):
            load_judge_settings_from_env()
