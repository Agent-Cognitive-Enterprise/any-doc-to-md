"""
Tests for format_converters/tournament/audit.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.format_converters.tournament.audit import run_post_selection_audit_loop
from anydoc2md.format_converters.tournament.selector import SelectionResult
from anydoc2md.llm_judge import JudgeVerdict, JudgeViolation
from anydoc2md.output_qa.scoring import ScoreCard


def _traits() -> DocumentTraits:
    return DocumentTraits(
        file_type="pdf",
        page_count=5,
        image_count=2,
        table_count=1,
        word_count=500,
        is_scanned=False,
        is_image_heavy=False,
        is_table_heavy=False,
        is_multi_column=False,
        is_text_only=False,
        has_math=False,
    )


def _scorecard(name: str, score: float = 0.0) -> ScoreCard:
    return ScoreCard(
        adapter_name=name,
        total_score=score,
        check_scores={},
        fail_count=0,
        warn_count=0,
        pass_count=1,
    )


def _selection(*names: str) -> SelectionResult:
    ranked = [_scorecard(name, float(i)) for i, name in enumerate(names)]
    return SelectionResult(
        winner=names[0] if names else None,
        winner_score=0.0,
        ranked=ranked,
        disqualified={},
        near_tie=False,
        near_tie_adapters=[],
    )


def _adapter_result(name: str, staging_root: Path) -> AdapterResult:
    staging = staging_root / name
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "index.md").write_text(f"# {name}", encoding="utf-8")
    return AdapterResult(
        method_name=name,
        method_version="1",
        command_invoked="",
        exit_code=0,
        staging_dir=staging,
        timing_ms=10,
        status="ok",
    )


def _accepted_verdict(name: str) -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence="high",
        reasoning="Looks acceptable.",
        notes={name: "acceptable"},
        model_used="test-model",
        tokens_used=100,
        violations=[],
    )


def _major_verdict(name: str) -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence="high",
        reasoning="Material issues detected.",
        notes={name: "major issues"},
        model_used="test-model",
        tokens_used=100,
        violations=[
            JudgeViolation(
                type="reading_order",
                severity="major",
                count=1,
                pages=[2],
                confidence=0.9,
                evidence="Paragraphs are out of order.",
                root_cause="multicolumn merge",
            )
        ],
    )


def _major_verdict_many(name: str, count: int) -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence="high",
        reasoning="Material issues detected.",
        notes={name: "major issues"},
        model_used="test-model",
        tokens_used=100,
        violations=[
            JudgeViolation(
                type="reading_order",
                severity="major",
                count=count,
                pages=[2],
                confidence=0.9,
                evidence="Paragraphs are out of order.",
                root_cause="multicolumn merge",
            )
        ],
    )


def _error_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter="",
        confidence="error",
        reasoning="",
        notes={},
        model_used="test-model",
        tokens_used=0,
        error="judge unavailable",
    )


class TestAuditLoop:
    def test_accepts_first_candidate_when_audit_passes(self, tmp_path: Path) -> None:
        selection = _selection("inhouse", "docling")
        adapters = [_adapter_result("inhouse", tmp_path), _adapter_result("docling", tmp_path)]
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            side_effect=lambda markdown_path, output_path: output_path,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            return_value=_accepted_verdict("inhouse"),
        ) as judge_mock:
            result = run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
            )
        assert result.winner == "inhouse"
        assert result.audits[0].status == "accepted"
        judge_mock.assert_called_once()

    def test_rejects_major_and_moves_to_next_candidate(self, tmp_path: Path) -> None:
        selection = _selection("docling", "inhouse")
        adapters = [_adapter_result("docling", tmp_path), _adapter_result("inhouse", tmp_path)]
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            side_effect=lambda markdown_path, output_path: output_path,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            side_effect=[_major_verdict_many("docling", 2), _accepted_verdict("inhouse")],
        ):
            result = run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
            )
        assert result.winner == "inhouse"
        assert [audit.status for audit in result.audits] == ["rejected_major", "accepted"]
        assert result.remediation_plan is not None
        assert result.remediation_plan.target_adapter == "inhouse"
        assert result.audits[0].penalty_points == 24.0
        assert result.audits[0].rescored_total == 24.0

    def test_accepts_penalized_major_candidate_when_it_stays_ahead(self, tmp_path: Path) -> None:
        selection = SelectionResult(
            winner="docling",
            winner_score=0.0,
            ranked=[_scorecard("docling", 0.0), _scorecard("inhouse", 20.0)],
            disqualified={},
            near_tie=False,
            near_tie_adapters=[],
        )
        adapters = [_adapter_result("docling", tmp_path), _adapter_result("inhouse", tmp_path)]
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            side_effect=lambda markdown_path, output_path: output_path,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            return_value=_major_verdict("docling"),
        ):
            result = run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
            )
        assert result.winner == "docling"
        assert [audit.status for audit in result.audits] == ["accepted_penalized_major"]
        assert result.remediation_plan is not None

    def test_escalates_when_major_findings_exhaust_audit_budget(self, tmp_path: Path) -> None:
        selection = _selection("docling", "markitdown", "inhouse", "pandoc")
        adapters = [_adapter_result(name, tmp_path) for name in ("docling", "markitdown", "inhouse", "pandoc")]
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            side_effect=lambda markdown_path, output_path: output_path,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            side_effect=[
                _major_verdict("docling"),
                _major_verdict("markitdown"),
                _major_verdict("inhouse"),
            ],
        ):
            result = run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
                max_attempts=3,
            )
        assert result.winner is None
        assert result.escalated is True
        assert len(result.audits) == 3

    def test_audit_error_falls_back_to_current_candidate(self, tmp_path: Path) -> None:
        selection = _selection("inhouse", "docling")
        adapters = [_adapter_result("inhouse", tmp_path), _adapter_result("docling", tmp_path)]
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            side_effect=lambda markdown_path, output_path: output_path,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            return_value=_error_verdict(),
        ):
            result = run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
            )
        assert result.winner == "inhouse"
        assert result.audits[0].status == "audit_error_fallback"

    def test_rendered_audit_pdf_path_is_passed_to_judge(self, tmp_path: Path) -> None:
        selection = _selection("inhouse")
        adapters = [_adapter_result("inhouse", tmp_path)]
        rendered_pdf = tmp_path / "inhouse" / "audit_candidate.pdf"
        with patch(
            "anydoc2md.format_converters.tournament.audit.render_markdown_to_audit_pdf",
            return_value=rendered_pdf,
        ), patch(
            "anydoc2md.format_converters.tournament.audit.judge_candidate_against_source",
            return_value=_accepted_verdict("inhouse"),
        ) as judge_mock:
            run_post_selection_audit_loop(
                selection=selection,
                adapter_results=adapters,
                source_path=tmp_path / "doc.pdf",
                traits=_traits(),
            )
        assert judge_mock.call_args.kwargs["audit_pdf_path"] == rendered_pdf
