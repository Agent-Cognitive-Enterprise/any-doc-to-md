from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

import fitz

from anydoc2md._llm_judge_pdf_windows import (
    PDF_AUDIT_WINDOW_PAGES,
    PdfAuditWindow,
    build_pdf_audit_windows,
    build_windowed_audit_prompt,
)
from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md._llm_judge_pdf_issue_reviewer import PDF_ISSUE_REVIEW_MAX_ATTEMPTS
from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.llm_judge import judge_candidate_against_source
from anydoc2md.settings import JudgeSettings


def _traits() -> DocumentTraits:
    return DocumentTraits(
        file_type="pdf",
        page_count=12,
        image_count=1,
        table_count=1,
        word_count=1200,
        is_scanned=False,
        is_image_heavy=False,
        is_table_heavy=False,
        is_multi_column=False,
        is_text_only=False,
        has_math=False,
    )


def _adapter_result(name: str, staging_root: Path, md: str = "# Doc") -> AdapterResult:
    staging = staging_root / name
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


def _make_pdf(path: Path, *, pages: int, prefix: str) -> None:
    doc = fitz.open()
    for page_number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"{prefix} page {page_number}. "
            f"Section {page_number}. " * 12,
        )
    doc.save(path)
    doc.close()


def _judge_settings(*, pdf_concurrency: int = 1) -> JudgeSettings:
    return JudgeSettings(
        url="http://localhost:1234/v1",
        model="test-model",
        pdf_concurrency=pdf_concurrency,
    )


def test_build_pdf_audit_windows_splits_source_pages_and_maps_candidate_pages(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=12, prefix="Source")
    _make_pdf(candidate_pdf, pages=10, prefix="Candidate")

    windows = build_pdf_audit_windows(source_pdf, candidate_pdf)

    assert len(windows) == 2
    assert windows[0].source_page_start == 1
    assert windows[0].source_page_end == PDF_AUDIT_WINDOW_PAGES
    assert windows[1].source_page_start == 7
    assert windows[1].source_page_end == 12
    assert windows[0].candidate_page_start == 1
    assert windows[0].candidate_page_end >= 5
    assert windows[1].candidate_page_end == 10


def test_build_windowed_audit_prompt_mentions_page_ranges() -> None:
    window = PdfAuditWindow(
        window_index=1,
        total_windows=3,
        source_page_start=1,
        source_page_end=6,
        source_page_count=18,
        candidate_page_start=1,
        candidate_page_end=5,
        candidate_page_count=15,
        source_excerpt="Source page 1:\nAlpha",
        candidate_excerpt="Candidate page 1:\nBeta",
    )

    system, user = build_windowed_audit_prompt("inhouse", _traits(), window)

    assert "absolute SOURCE page numbers" in system
    assert "Do NOT treat different page counts" in system
    assert "reflowed audit render of Markdown" in system
    assert "Audit window 1/3" in user
    assert "Source pages: 1-6 of 18" in user
    assert "Candidate pages: 1-5 of 15" in user
    assert "not page-for-page visual alignment" in user


def test_judge_candidate_against_source_aggregates_windowed_pdf_violations(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=12, prefix="Source")
    _make_pdf(candidate_pdf, pages=10, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)
    issues = [
        PdfSuspectedIssue(
            issue_type="suspected_content_mismatch",
            description="Issue 1",
            source_page_start=1,
            source_page_end=3,
            candidate_page_start=1,
            candidate_page_end=4,
            source_excerpt="Source page 1:\nAlpha",
            candidate_excerpt="Candidate page 1:\nBeta",
        ),
        PdfSuspectedIssue(
            issue_type="suspected_content_mismatch",
            description="Issue 2",
            source_page_start=7,
            source_page_end=9,
            candidate_page_start=6,
            candidate_page_end=8,
            source_excerpt="Source page 7:\nGamma",
            candidate_excerpt="Candidate page 6:\nDelta",
        ),
    ]

    responses = [
        (
            json.dumps(
                {
                    "preferred": "inhouse",
                    "confidence": "high",
                    "reasoning": "Window 1 issues.",
                    "notes": {"inhouse": "w1"},
                    "violations": [
                        {
                            "type": "reading_order",
                            "severity": "major",
                            "count": 1,
                            "pages": [2],
                            "confidence": 0.9,
                            "evidence": "Paragraphs are out of order.",
                            "root_cause": "multicolumn merge",
                        }
                    ],
                }
            ),
            111,
        ),
        (
            json.dumps(
                {
                    "preferred": "inhouse",
                    "confidence": "medium",
                    "reasoning": "Window 2 issues.",
                    "notes": {"inhouse": "w2"},
                    "violations": [
                        {
                            "type": "reading_order",
                            "severity": "major",
                            "count": 1,
                            "pages": [8],
                            "confidence": 0.8,
                            "evidence": "Paragraphs are out of order.",
                            "root_cause": "multicolumn merge",
                        }
                    ],
                }
            ),
            222,
        ),
    ]

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=issues,
    ), patch("anydoc2md.llm_judge._call_lm_studio", side_effect=responses):
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(),
        )

    assert verdict.succeeded is True
    assert verdict.confidence == "medium"
    assert verdict.tokens_used == 333
    assert len(verdict.window_verdicts) == 2
    assert len(verdict.violations) == 1
    assert verdict.violations[0].pages == [2, 8]
    assert verdict.violations[0].count == 2


def test_judge_candidate_against_source_reviews_pdf_issues_concurrently_in_order(
    tmp_path: Path,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)
    issues = [
        PdfSuspectedIssue(
            issue_type="suspected_content_mismatch",
            description=f"Issue {index}",
            source_page_start=index,
            source_page_end=index,
            candidate_page_start=index,
            candidate_page_end=index,
            source_excerpt=f"Source page {index}:\nAlpha",
            candidate_excerpt=f"Candidate page {index}:\nBeta",
        )
        for index in range(1, 5)
    ]
    active_calls = 0
    max_active_calls = 0
    lock = threading.Lock()

    def fake_call(_system: str, user: str, _settings: JudgeSettings) -> tuple[str, int]:
        nonlocal active_calls, max_active_calls
        issue_number = int(user.split("## Suspected issue ", 1)[1].split("/", 1)[0])
        with lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        try:
            time.sleep(0.02)
            return (
                json.dumps(
                    {
                        "preferred": "inhouse",
                        "confidence": "high",
                        "reasoning": f"Window {issue_number} ok.",
                        "notes": {"inhouse": "ok"},
                        "violations": [
                            {
                                "type": "reading_order",
                                "severity": "minor",
                                "count": 1,
                                "pages": [issue_number],
                                "confidence": 0.8,
                                "evidence": "brief",
                                "root_cause": "test",
                            }
                        ],
                    }
                ),
                10 + issue_number,
            )
        finally:
            with lock:
                active_calls -= 1

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=issues,
    ), patch("anydoc2md.llm_judge._call_lm_studio", side_effect=fake_call):
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(pdf_concurrency=2),
        )

    assert verdict.succeeded is True
    assert max_active_calls > 1
    assert [window.window_index for window in verdict.window_verdicts] == [1, 2, 3, 4]
    assert verdict.tokens_used == 50


def test_judge_candidate_against_source_returns_error_when_window_call_fails(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    candidate_pdf = tmp_path / "candidate.pdf"
    _make_pdf(source_pdf, pages=6, prefix="Source")
    _make_pdf(candidate_pdf, pages=6, prefix="Candidate")
    candidate = _adapter_result("inhouse", tmp_path)
    issues = [
        PdfSuspectedIssue(
            issue_type="suspected_content_mismatch",
            description="Issue 1",
            source_page_start=1,
            source_page_end=3,
            candidate_page_start=1,
            candidate_page_end=3,
            source_excerpt="Source page 1:\nAlpha",
            candidate_excerpt="Candidate page 1:\nBeta",
        )
    ]

    with patch(
        "anydoc2md.llm_judge.detect_pdf_suspected_issues",
        return_value=issues,
    ), patch("anydoc2md.llm_judge._call_lm_studio", side_effect=RuntimeError("boom")) as call_mock:
        verdict = judge_candidate_against_source(
            candidate,
            source_pdf,
            _traits(),
            audit_pdf_path=candidate_pdf,
            settings=_judge_settings(),
        )

    assert verdict.succeeded is False
    assert call_mock.call_count == PDF_ISSUE_REVIEW_MAX_ATTEMPTS
    assert "Issue-focused PDF review" in verdict.error
    assert f"after {PDF_ISSUE_REVIEW_MAX_ATTEMPTS} attempts" in verdict.error
