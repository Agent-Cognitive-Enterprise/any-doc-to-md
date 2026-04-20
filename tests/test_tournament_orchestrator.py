"""
Tests for format_converters/tournament/orchestrator.py.

Heavy I/O is mocked so these tests only verify orchestration:

- adapter selection and tournament wiring
- audit-loop result adoption
- winner promotion
- escalation and no-winner paths
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.format_converters.tournament.audit import (
    AuditLoopResult,
    CandidateAudit,
)
from anydoc2md.format_converters.tournament.orchestrator import (
    WINNER_DIR_NAME,
    TournamentResult,
    run_full_tournament,
)
from anydoc2md.format_converters.tournament.remediation import RemediationPlan
from anydoc2md.format_converters.tournament.selector import (
    NEAR_TIE_THRESHOLD,
    SelectionResult,
)
from anydoc2md.llm_judge import JudgeVerdict, JudgeViolation
from anydoc2md.output_qa.scoring import ScoreCard

MOCK_BASE = "anydoc2md.format_converters.tournament.orchestrator"


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


def _verdict(name: str, confidence: str = "high") -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence=confidence,
        reasoning="Looks good.",
        notes={name: "acceptable"},
        model_used="test-model",
        tokens_used=100,
    )


def _verdict_with_major(name: str) -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence="high",
        reasoning="Major issues found.",
        notes={name: "major findings"},
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


def _audit_result(
    *,
    winner: str | None,
    verdict: JudgeVerdict | None = None,
    remediation_plan: RemediationPlan | None = None,
    audit_history: list[CandidateAudit] | None = None,
    escalated: bool = False,
) -> AuditLoopResult:
    return AuditLoopResult(
        winner=winner,
        final_verdict=verdict,
        remediation_plan=remediation_plan,
        audits=audit_history or [],
        escalated=escalated,
    )


def _patch_base(
    tmp_path: Path,
    *,
    adapter_names: list[str],
    selection: SelectionResult,
    audit_result: AuditLoopResult,
):
    adapters = [_adapter_result(name, tmp_path) for name in adapter_names]
    classify_mock = patch(f"{MOCK_BASE}.classify", return_value=_traits())
    tournament_mock = patch(f"{MOCK_BASE}.run_tournament", return_value=adapters)
    selector_mock = patch(f"{MOCK_BASE}.select_candidate", return_value=selection)
    audit_mock = patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result)
    return classify_mock, tournament_mock, selector_mock, audit_mock


class TestTournamentResultContract:
    def test_to_dict_has_required_keys(self, tmp_path: Path) -> None:
        result = TournamentResult(
            source_path=tmp_path / "doc.pdf",
            traits=_traits(),
            adapter_results=[],
            selection=_selection("inhouse"),
            judge_verdict=None,
            remediation_plan=None,
            audit_history=[],
            winner="inhouse",
            winner_staging_dir=tmp_path / WINNER_DIR_NAME,
            promoted=True,
            escalated=False,
        )
        data = result.to_dict()
        for key in (
            "source_path",
            "winner",
            "winner_staging_dir",
            "promoted",
            "traits",
            "selection",
            "judge_verdict",
            "audit_history",
            "adapter_timing_ms",
            "escalated",
        ):
            assert key in data


class TestOrchestratorFlow:
    def test_default_selection_uses_all_implemented_adapters(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        staging_root = tmp_path / "staging"
        source_path.write_bytes(b"%PDF-1.4")
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))

        with patch(f"{MOCK_BASE}.available_adapter_names", return_value=["inhouse", "markitdown", "docling", "pandoc", "marker"]) as adapters_mock, \
             patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[]) as tournament_mock, \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection) as selector_mock, \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result) as audit_mock:
            run_full_tournament(source_path, staging_root, adapters=None, promote=False)

        adapters_mock.assert_called_once_with()
        tournament_mock.assert_called_once_with(
            source_path,
            staging_root,
            ["inhouse", "markitdown", "docling", "pandoc", "marker"],
            timeout_s=600,
        )
        selector_mock.assert_called_once_with(
            source_path,
            staging_root,
            ["inhouse", "markitdown", "docling", "pandoc", "marker"],
            near_tie_threshold=NEAR_TIE_THRESHOLD,
        )
        audit_mock.assert_called_once()

    def test_audit_loop_winner_becomes_final_winner(self, tmp_path: Path) -> None:
        selection = _selection("docling", "docling", "inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))
        classify_p, tour_p, sel_p, audit_p = _patch_base(
            tmp_path,
            adapter_names=["docling", "inhouse"],
            selection=selection,
            audit_result=audit_result,
        )
        with classify_p, tour_p, sel_p, audit_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner == "inhouse"
        assert result.judge_verdict is not None
        assert result.judge_verdict.preferred_adapter == "inhouse"

    def test_remediation_plan_and_audit_history_are_stored(self, tmp_path: Path) -> None:
        selection = _selection("docling", "docling", "inhouse")
        remediation = RemediationPlan(
            source_path=str(tmp_path / "doc.pdf"),
            target_adapter="inhouse",
            preferred_adapter="docling",
            compare_against="docling",
            summary="1 remediation task",
            tasks=[],
        )
        audit_history = [
            CandidateAudit("docling", _verdict_with_major("docling"), "rejected_major"),
            CandidateAudit("inhouse", _verdict("inhouse"), "accepted"),
        ]
        audit_result = _audit_result(
            winner="inhouse",
            verdict=_verdict("inhouse"),
            remediation_plan=remediation,
            audit_history=audit_history,
        )
        classify_p, tour_p, sel_p, audit_p = _patch_base(
            tmp_path,
            adapter_names=["docling", "inhouse"],
            selection=selection,
            audit_result=audit_result,
        )
        with classify_p, tour_p, sel_p, audit_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.remediation_plan is not None
        assert result.remediation_plan.target_adapter == "inhouse"
        assert len(result.audit_history) == 2
        assert result.to_dict()["audit_history"][0]["status"] == "rejected_major"

    def test_escalation_is_preserved_when_audit_loop_fails_to_accept(self, tmp_path: Path) -> None:
        selection = _selection("docling", "docling", "inhouse")
        audit_result = _audit_result(
            winner=None,
            verdict=_verdict_with_major("docling"),
            audit_history=[CandidateAudit("docling", _verdict_with_major("docling"), "rejected_major")],
            escalated=True,
        )
        classify_p, tour_p, sel_p, audit_p = _patch_base(
            tmp_path,
            adapter_names=["docling", "inhouse"],
            selection=selection,
            audit_result=audit_result,
        )
        with classify_p, tour_p, sel_p, audit_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner is None
        assert result.escalated is True
        assert result.promoted is False


class TestPromotionBehavior:
    def test_promotes_winner_dir(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        (staging / "inhouse").mkdir(parents=True, exist_ok=True)
        (staging / "inhouse" / "index.md").write_text("# Inhouse", encoding="utf-8")
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[_adapter_result("inhouse", staging)]), \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection), \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result):
            result = run_full_tournament(tmp_path / "doc.pdf", staging)

        assert result.promoted is True
        assert result.winner_staging_dir == staging / WINNER_DIR_NAME
        assert (staging / WINNER_DIR_NAME / "index.md").exists()

    def test_promote_false_points_to_adapter_dir(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))
        classify_p, tour_p, sel_p, audit_p = _patch_base(
            tmp_path,
            adapter_names=["inhouse"],
            selection=selection,
            audit_result=audit_result,
        )
        with classify_p, tour_p, sel_p, audit_p:
            result = run_full_tournament(tmp_path / "doc.pdf", staging, promote=False)
        assert result.promoted is False
        assert result.winner_staging_dir == staging / "inhouse"

    def test_no_winner_means_no_promotion(self, tmp_path: Path) -> None:
        selection = SelectionResult(
            winner=None,
            winner_score=0.0,
            ranked=[],
            disqualified={"inhouse": "empty"},
            near_tie=False,
            near_tie_adapters=[],
        )
        audit_result = _audit_result(winner=None)
        classify_p, tour_p, sel_p, audit_p = _patch_base(
            tmp_path,
            adapter_names=["inhouse"],
            selection=selection,
            audit_result=audit_result,
        )
        with classify_p, tour_p, sel_p, audit_p:
            result = run_full_tournament(tmp_path / "doc.pdf", tmp_path / "staging")
        assert result.winner is None
        assert result.winner_staging_dir is None
        assert result.promoted is False
