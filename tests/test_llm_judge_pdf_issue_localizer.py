from __future__ import annotations

from pathlib import Path

import fitz

from anydoc2md._llm_judge_pdf_issue_localizer import detect_pdf_suspected_issues


def _make_pdf(path: Path, page_texts: list[str]) -> None:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_detect_pdf_suspected_issues_returns_empty_for_matching_documents(tmp_path: Path) -> None:
    pages = [
        "Alpha introduction and legal foundations page one.",
        "Beta obligations and remedies page two.",
        "Gamma enforcement and compliance page three.",
    ]
    source = tmp_path / "source.pdf"
    candidate = tmp_path / "candidate.pdf"
    _make_pdf(source, pages)
    _make_pdf(candidate, pages)

    issues = detect_pdf_suspected_issues(source, candidate)

    assert issues == []


def test_detect_pdf_suspected_issues_localizes_mismatched_page(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    candidate = tmp_path / "candidate.pdf"
    _make_pdf(
        source,
        [
            "Alpha introduction and legal foundations page one.",
            "Beta obligations and remedies page two with indemnity clauses.",
            "Gamma enforcement and compliance page three.",
        ],
    )
    _make_pdf(
        candidate,
        [
            "Alpha introduction and legal foundations page one.",
            "Completely unrelated canine-assisted mediation worksheet and personality test content.",
            "Gamma enforcement and compliance page three.",
        ],
    )

    issues = detect_pdf_suspected_issues(source, candidate)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.source_page_start == 1
    assert issue.source_page_end == 3
    assert issue.candidate_page_start == 1
    assert issue.candidate_page_end == 3
    assert "page-anchor comparison" in issue.description
