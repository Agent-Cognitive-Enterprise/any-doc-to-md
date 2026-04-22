from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import fitz
import requests

from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md._llm_judge_rate_limit import rate_limit_retry_delay_s
from anydoc2md._llm_judge_types import JudgeCallResult
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.llm_judge import judge_candidate_against_source
from anydoc2md.settings import JUDGE_PROVIDER_CLAUDE, JUDGE_PROVIDER_OPENAI, JudgeSettings


def _traits() -> DocumentTraits:
    return DocumentTraits(
        file_type="pdf",
        page_count=6,
        image_count=1,
        table_count=1,
        word_count=600,
        is_scanned=False,
        is_image_heavy=False,
        is_table_heavy=False,
        is_multi_column=False,
        is_text_only=False,
        has_math=False,
    )


def _adapter_result(name: str, staging_root: Path) -> AdapterResult:
    staging = staging_root / name
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "index.md").write_text("# Doc", encoding="utf-8")
    return AdapterResult(
        method_name=name,
        method_version="1",
        command_invoked="",
        exit_code=0,
        staging_dir=staging,
        timing_ms=10,
        status="ok",
    )


def _make_pdf(path: Path, *, pages: int, prefix: str) -> None:
    doc = fitz.open()
    for page_number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"{prefix} page {page_number}.")
    doc.save(path)
    doc.close()


def _issue() -> PdfSuspectedIssue:
    return PdfSuspectedIssue(
        issue_type="suspected_content_mismatch",
        description="Issue 1",
        source_page_start=1,
        source_page_end=3,
        candidate_page_start=1,
        candidate_page_end=3,
        source_excerpt="Source page 1:\nAlpha",
        candidate_excerpt="Candidate page 1:\nBeta",
    )


def _issue_response() -> str:
    return json.dumps(
        {
            "preferred": "inhouse",
            "confidence": "high",
            "reasoning": "Window reviewed.",
            "notes": {"inhouse": "reviewed"},
            "violations": [
                {
                    "type": "reading_order",
                    "severity": "minor",
                    "count": 1,
                    "pages": [1],
                    "confidence": 0.8,
                    "evidence": "brief",
                    "root_cause": "test",
                }
            ],
        }
    )


def _judge_settings() -> JudgeSettings:
    return JudgeSettings(url="http://localhost:1234/v1", model="test-model")


def _cloud_judge_settings(provider: str) -> JudgeSettings:
    return JudgeSettings(
        url="https://api.example.test/v1",
        model="test-model",
        provider=provider,
        api_key="sk-test",
    )


def _http_error(status_code: int, headers: dict[str, str] | None = None) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response.headers.update(headers or {})
    return requests.HTTPError(f"{status_code} error", response=response)


def test_pdf_issue_review_retries_transient_call_failure(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=[_issue()],
    ), patch(
        "anydoc2md.llm_judge._call_lm_studio",
        side_effect=[RuntimeError("temporary 500"), (_issue_response(), 123)],
    ) as call_mock:
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(),
        )

    assert verdict.succeeded is True
    assert call_mock.call_count == 2
    assert verdict.tokens_used == 123
    assert len(verdict.window_verdicts) == 1


def test_pdf_issue_review_retries_unrepaired_json_and_counts_tokens(
    tmp_path: Path,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=[_issue()],
    ), patch(
        "anydoc2md.llm_judge._call_lm_studio",
        side_effect=[("not json", 11), (_issue_response(), 22)],
    ) as call_mock:
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(),
        )

    assert verdict.succeeded is True
    assert call_mock.call_count == 2
    assert verdict.tokens_used == 33
    assert verdict.window_verdicts[0].tokens_used == 33


def test_pdf_issue_review_records_input_and_output_tokens(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=[_issue()],
    ), patch(
        "anydoc2md.llm_judge._call_lm_studio",
        return_value=JudgeCallResult(
            text=_issue_response(),
            tokens_used=29,
            input_tokens=23,
            output_tokens=6,
        ),
    ):
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(),
        )

    assert verdict.succeeded is True
    assert verdict.tokens_used == 29
    assert verdict.input_tokens == 23
    assert verdict.output_tokens == 6
    assert verdict.window_verdicts[0].input_tokens == 23
    assert verdict.window_verdicts[0].output_tokens == 6


def test_pdf_issue_review_backs_off_on_429_retry_after(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=[_issue()],
    ), patch(
        "anydoc2md.llm_judge._call_lm_studio",
        side_effect=[
            _http_error(429, {"retry-after": "3"}),
            JudgeCallResult(
                text=_issue_response(),
                tokens_used=29,
                input_tokens=23,
                output_tokens=6,
            ),
        ],
    ) as call_mock, patch(
        "anydoc2md._llm_judge_pdf_issue_reviewer.time.sleep"
    ) as sleep_mock:
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_cloud_judge_settings(JUDGE_PROVIDER_CLAUDE),
        )

    assert verdict.succeeded is True
    assert call_mock.call_count == 2
    sleep_mock.assert_called_once_with(3.0)


def test_rate_limit_retry_delay_uses_provider_specific_fallbacks() -> None:
    err = _http_error(429)

    assert rate_limit_retry_delay_s(
        err,
        attempt=2,
        settings=_cloud_judge_settings(JUDGE_PROVIDER_CLAUDE),
    ) == 16.0
    assert rate_limit_retry_delay_s(
        err,
        attempt=2,
        settings=_cloud_judge_settings(JUDGE_PROVIDER_OPENAI),
    ) == 4.0
