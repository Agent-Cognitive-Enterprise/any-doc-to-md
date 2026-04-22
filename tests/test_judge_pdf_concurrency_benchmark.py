from __future__ import annotations

from pathlib import Path

import pytest

from anydoc2md._llm_judge_pdf_issue_localizer import PdfSuspectedIssue
from anydoc2md._llm_judge_types import JudgeVerdict, JudgeWindowVerdict
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.judge_pdf_concurrency_benchmark_core import (
    BenchmarkAttempt,
    BenchmarkCase,
    parse_case_spec,
    parse_concurrency_levels,
    run_benchmark_matrix,
    summarize_attempts,
)
from anydoc2md.settings import JudgeSettings
import anydoc2md.judge_pdf_concurrency_benchmark_core as benchmark_core


def _traits() -> DocumentTraits:
    return DocumentTraits(
        file_type="pdf",
        page_count=3,
        image_count=0,
        table_count=0,
        word_count=0,
        is_scanned=False,
        is_image_heavy=False,
        is_table_heavy=False,
        is_multi_column=False,
        is_text_only=False,
        has_math=False,
    )


def _issue() -> PdfSuspectedIssue:
    return PdfSuspectedIssue(
        issue_type="suspected_content_mismatch",
        description="Issue",
        source_page_start=1,
        source_page_end=1,
        candidate_page_start=1,
        candidate_page_end=1,
        source_excerpt="Source page 1:\nAlpha",
        candidate_excerpt="Candidate page 1:\nBeta",
    )


def test_parse_case_spec_defaults_candidate_to_audit_parent(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    audit = tmp_path / "winner" / "audit_candidate.pdf"

    case = parse_case_spec(f"{source}::{audit}")

    assert case.source_pdf_path == source.resolve()
    assert case.audit_pdf_path == audit.resolve()
    assert case.candidate_name == "winner"
    assert case.case_id == "source"


def test_parse_case_spec_accepts_explicit_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    audit = tmp_path / "audit.pdf"

    case = parse_case_spec(f"{source}::{audit}::markitdown")

    assert case.candidate_name == "markitdown"


def test_parse_concurrency_levels_validates_positive_ints() -> None:
    assert parse_concurrency_levels("1, 2,4,8") == [1, 2, 4, 8]

    with pytest.raises(ValueError):
        parse_concurrency_levels("1,0")

    with pytest.raises(ValueError):
        parse_concurrency_levels("x")


def test_summarize_attempts_groups_by_concurrency() -> None:
    attempts = [
        BenchmarkAttempt("a", 1, 1, True, 10.0, 100, 2, 1, "low", 1),
        BenchmarkAttempt("b", 1, 1, False, 12.0, 0, 0, 0, "error", 1, "boom"),
        BenchmarkAttempt("a", 4, 1, True, 3.0, 100, 2, 1, "low", 4),
    ]

    summary = summarize_attempts(attempts)

    assert summary[0]["concurrency"] == 1
    assert summary[0]["success_count"] == 1
    assert summary[0]["error_count"] == 1
    assert summary[0]["mean_elapsed_s"] == 10.0
    assert summary[1]["concurrency"] == 4
    assert summary[1]["max_active_calls"] == 4


def test_run_benchmark_matrix_passes_each_concurrency_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    audit = tmp_path / "audit_candidate.pdf"
    source.write_bytes(b"source")
    audit.write_bytes(b"audit")
    case = BenchmarkCase(
        case_id="case",
        source_pdf_path=source,
        audit_pdf_path=audit,
        candidate_name="inhouse",
    )
    seen_concurrency: list[int] = []

    def fake_judge(**kwargs):
        settings = kwargs["settings"]
        seen_concurrency.append(settings.pdf_concurrency)
        return JudgeVerdict(
            preferred_adapter="inhouse",
            confidence="low",
            reasoning="ok",
            notes={},
            model_used=settings.model,
            tokens_used=10,
            window_verdicts=[
                JudgeWindowVerdict(
                    window_index=1,
                    total_windows=1,
                    source_page_start=1,
                    source_page_end=1,
                    candidate_page_start=1,
                    candidate_page_end=1,
                    confidence="low",
                    reasoning="ok",
                    tokens_used=10,
                )
            ],
        )

    monkeypatch.setattr(benchmark_core, "_pdf_traits", lambda _path: _traits())
    monkeypatch.setattr(benchmark_core, "detect_pdf_suspected_issues", lambda *_args: [_issue()])
    monkeypatch.setattr(benchmark_core, "judge_candidate_against_source_issues", fake_judge)

    result = run_benchmark_matrix(
        cases=[case],
        concurrency_levels=[1, 4],
        repeats=2,
        base_settings=JudgeSettings(url="http://judge.local/v1", model="test-model"),
    )

    assert seen_concurrency == [1, 1, 4, 4]
    assert len(result["attempts"]) == 4
    assert result["summary"][0]["success_count"] == 2
    assert result["cases"][0]["issue_count"] == 1
