"""
Runtime decision and settings tests for anydoc2md.llm_judge.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests._llm_judge_helpers import (
    adapter_result,
    judge_settings,
    mock_response,
    traits,
)

from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md.llm_judge import judge_candidate_against_source, judge_near_tie
from anydoc2md.settings import (
    AnyDocToMdConfigError,
    JudgeSettings,
    load_judge_settings_from_env,
)


class TestJudgeNearTie:
    def test_single_candidate_shortcut(self, tmp_path: Path) -> None:
        candidate = adapter_result("only", tmp_path, "# Only")
        verdict = judge_near_tie([candidate], Path("/src/doc.pdf"), traits())
        assert verdict.preferred_adapter == "only"
        assert verdict.succeeded is True
        assert verdict.tokens_used == 0

    def test_empty_candidates_shortcut(self, tmp_path: Path) -> None:
        verdict = judge_near_tie([], Path("/src/doc.pdf"), traits())
        assert verdict.preferred_adapter == ""

    def test_missing_env_returns_error_verdict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        monkeypatch.delenv("ANYDOC2MD_JUDGE_URL", raising=False)
        monkeypatch.delenv("ANYDOC2MD_JUDGE_MODEL", raising=False)

        verdict = judge_near_tie([a, b], Path("/src/doc.pdf"), traits())

        assert verdict.confidence == "error"
        assert "Missing required anydoc2md judge env vars" in verdict.error

    def test_happy_path_mocked(self, tmp_path: Path) -> None:
        a = adapter_result("inhouse", tmp_path, "# Inhouse\n\nGood text.")
        b = adapter_result("docling", tmp_path, "# Docling\n\nAlso good.")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = mock_response("inhouse")
            verdict = judge_near_tie(
                [a, b],
                Path("/src/doc.pdf"),
                traits(),
                settings=judge_settings(),
            )

        assert verdict.preferred_adapter == "inhouse"
        assert verdict.confidence == "high"
        assert verdict.succeeded is True
        assert verdict.tokens_used == 512
        assert verdict.violations[0].type == "reading_order"

    def test_network_failure_returns_error_verdict(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.side_effect = Exception("Connection refused")
            verdict = judge_near_tie(
                [a, b],
                Path("/src/doc.pdf"),
                traits(),
                settings=judge_settings(),
            )

        assert verdict.confidence == "error"
        assert verdict.preferred_adapter == ""
        assert "Connection refused" in verdict.error

    def test_custom_model_passed_through(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        settings = judge_settings(model="qwen/qwen3-32b")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = mock_response("a")
            verdict = judge_near_tie(
                [a, b],
                Path("/src/doc.pdf"),
                traits(),
                settings=settings,
            )

        assert verdict.model_used == "qwen/qwen3-32b"
        call_kwargs = mock_req.post.call_args
        assert "qwen/qwen3-32b" in str(call_kwargs)

    def test_custom_url_passed_through(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        settings = judge_settings(url="http://localhost:9999/v1")

        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = mock_response("a")
            judge_near_tie(
                [a, b],
                Path("/src/doc.pdf"),
                traits(),
                settings=settings,
            )

        url_called = mock_req.post.call_args[0][0]
        assert "localhost:9999" in url_called


class TestJudgeCandidateAgainstSource:
    def test_happy_path(self, tmp_path: Path) -> None:
        candidate = adapter_result("inhouse", tmp_path, "# Inhouse")
        audit_pdf = tmp_path / "audit.pdf"
        audit_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.return_value = mock_response("inhouse")
            verdict = judge_candidate_against_source(
                candidate,
                Path("/src/doc.pdf"),
                traits(),
                audit_pdf_path=audit_pdf,
                settings=judge_settings(),
            )
        assert verdict.succeeded is True
        assert verdict.preferred_adapter == "inhouse"

    def test_call_failure_returns_error_verdict(self, tmp_path: Path) -> None:
        candidate = adapter_result("inhouse", tmp_path, "# Inhouse")
        audit_pdf = tmp_path / "audit.pdf"
        audit_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        with patch("anydoc2md.llm_judge.requests") as mock_req:
            mock_req.post.side_effect = RuntimeError("boom")
            verdict = judge_candidate_against_source(
                candidate,
                Path("/src/doc.pdf"),
                traits(),
                audit_pdf_path=audit_pdf,
                settings=judge_settings(),
            )
        assert verdict.succeeded is False
        assert "boom" in verdict.error

    def test_pdf_audit_skips_llm_when_no_suspected_issues(self, tmp_path: Path) -> None:
        candidate = adapter_result("inhouse", tmp_path, "# Inhouse")
        source_pdf = tmp_path / "source.pdf"
        audit_pdf = tmp_path / "audit.pdf"
        source_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        audit_pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        with patch(
            "anydoc2md.llm_judge.detect_pdf_suspected_issues",
            return_value=[],
        ), patch("anydoc2md.llm_judge._call_lm_studio") as call_mock:
            verdict = judge_candidate_against_source(
                candidate,
                source_pdf,
                traits(),
                audit_pdf_path=audit_pdf,
                settings=judge_settings(),
            )

        call_mock.assert_not_called()
        assert verdict.succeeded is True
        assert verdict.tokens_used == 0
        assert verdict.violations == []

    def test_pdf_audit_reviews_only_suspected_issues(self, tmp_path: Path) -> None:
        candidate = adapter_result("inhouse", tmp_path, "# Inhouse")
        source_pdf = tmp_path / "source.pdf"
        audit_pdf = tmp_path / "audit.pdf"
        source_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        audit_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        suspected = PdfSuspectedIssue(
            issue_type="suspected_content_mismatch",
            description="Low anchor coverage on pages 3-4.",
            source_page_start=2,
            source_page_end=5,
            candidate_page_start=2,
            candidate_page_end=6,
            source_excerpt="Source page 2:\nAlpha",
            candidate_excerpt="Candidate page 2:\nBeta",
        )
        response = json.dumps(
            {
                "preferred": "inhouse",
                "confidence": "medium",
                "reasoning": "Confirmed one issue.",
                "notes": {"inhouse": "issue confirmed"},
                "violations": [
                    {
                        "type": "missing_content",
                        "severity": "major",
                        "count": 1,
                        "pages": [3],
                        "confidence": 0.9,
                        "evidence": "Paragraph missing.",
                        "root_cause": "bad merge",
                    }
                ],
            }
        )

        with patch(
            "anydoc2md.llm_judge.detect_pdf_suspected_issues",
            return_value=[suspected],
        ), patch(
            "anydoc2md.llm_judge._call_lm_studio",
            return_value=(response, 321),
        ) as call_mock:
            verdict = judge_candidate_against_source(
                candidate,
                source_pdf,
                traits(),
                audit_pdf_path=audit_pdf,
                settings=judge_settings(),
            )

        call_mock.assert_called_once()
        assert verdict.succeeded is True
        assert verdict.tokens_used == 321
        assert len(verdict.window_verdicts) == 1
        assert verdict.violations[0].type == "missing_content"


class TestJudgeSettings:
    def test_load_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MODEL", "qwen/test-model")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_TIMEOUT_S", "120")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MAX_TOKENS", "2048")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_DISABLE_THINKING", "false")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_TEMPERATURE", "0.2")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_PDF_CONCURRENCY", "7")

        settings = load_judge_settings_from_env()

        assert settings.url == "http://localhost:1234/v1"
        assert settings.model == "qwen/test-model"
        assert settings.timeout_s == 120
        assert settings.max_tokens == 2048
        assert settings.disable_thinking is False
        assert settings.temperature == 0.2
        assert settings.pdf_concurrency == 7

    def test_pdf_concurrency_defaults_to_four(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MODEL", "qwen/test-model")
        monkeypatch.delenv("ANYDOC2MD_JUDGE_PDF_CONCURRENCY", raising=False)

        settings = load_judge_settings_from_env()

        assert settings.pdf_concurrency == 4

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

    def test_invalid_pdf_concurrency_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANYDOC2MD_JUDGE_URL", "http://localhost:1234/v1")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_MODEL", "qwen/test-model")
        monkeypatch.setenv("ANYDOC2MD_JUDGE_PDF_CONCURRENCY", "0")

        with pytest.raises(AnyDocToMdConfigError):
            load_judge_settings_from_env()

    def test_explicit_invalid_pdf_concurrency_raises(self) -> None:
        with pytest.raises(AnyDocToMdConfigError):
            JudgeSettings(
                url="http://localhost:1234/v1",
                model="qwen/test-model",
                pdf_concurrency=0,
            )
