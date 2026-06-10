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
from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIR_REPORT_JSON,
    PARAGRAPH_REPAIRED_MD,
    apply_paragraph_continuity_repair,
    paragraph_repair_candidate_is_current,
)
from anydoc2md.settings import AUDIT_MODE_AUTO, AUDIT_MODE_LIGHT, JudgeSettings

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


def _row_sliced_fixture() -> str:
    rows = [
        "The inspection team arrived at the north intake",
        "after the first alarm and found that the overflow",
        "channel was carrying shallow water across the grated",
        "walkway while the upstream valve remained partially",
        "open and the temporary pump continued cycling",
        "every few minutes without recording a stable",
        "pressure reading.",
        "The operator reported that the same pattern",
        "had appeared during the previous storm and that",
        "the manual log showed brief pressure drops",
        "near the east manifold whenever the backup",
        "generator switched load.",
        "Because the site has limited lighting",
        "the team marked the affected panels with tape",
        "and postponed nonessential work until daylight.",
        "A follow up review should compare the sensor",
        "timestamps with pump starts and check whether",
        "the valve actuator is drifting under load",
        "before the next forecasted rain event.",
        "The maintenance lead asked that the morning crew",
        "verify the bypass pump before reopening the intake",
        "and record any new vibration near the manifold.",
    ]
    return "\n\n".join(rows) + "\n"


def _verdict(name: str, confidence: str = "high") -> JudgeVerdict:
    return JudgeVerdict(
        preferred_adapter=name,
        confidence=confidence,
        reasoning="Looks good.",
        notes={name: "acceptable"},
        model_used="test-model",
        tokens_used=100,
    )


def _judge_settings() -> JudgeSettings:
    return JudgeSettings(url="http://judge.local/v1/chat/completions", model="test-model")


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
            audit_mode=AUDIT_MODE_LIGHT,
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
            "audit_mode",
            "adapter_results",
            "adapter_timing_ms",
            "escalated",
        ):
            assert key in data


class TestOrchestratorFlow:
    def test_default_selection_uses_default_adapters(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        staging_root = tmp_path / "staging"
        source_path.write_bytes(b"%PDF-1.4")
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))

        with patch(f"{MOCK_BASE}.default_adapter_names", return_value=["inhouse"]) as adapters_mock, \
             patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament",
                   return_value=[_adapter_result("inhouse", staging_root)]) as tournament_mock, \
             patch(f"{MOCK_BASE}.apply_paragraph_continuity_repair"), \
             patch(f"{MOCK_BASE}.apply_fix_extensions"), \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection) as selector_mock, \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result) as audit_mock:
            run_full_tournament(
                source_path,
                staging_root,
                adapters=None,
                judge_settings=_judge_settings(),
                promote=False,
            )

        adapters_mock.assert_called_once_with()
        tournament_mock.assert_called_once_with(
            source_path,
            staging_root,
            ["inhouse"],
            timeout_s=600,
        )
        selector_mock.assert_called_once_with(
            source_path,
            staging_root,
            ["inhouse"],
            near_tie_threshold=NEAR_TIE_THRESHOLD,
        )
        audit_mock.assert_called_once()

    def test_explicit_adapters_remain_first_class_selectable(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        staging_root = tmp_path / "staging"
        source_path.write_bytes(b"%PDF-1.4")
        adapters = ["inhouse", "docling", "markitdown", "unstructured"]
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))

        with patch(f"{MOCK_BASE}.default_adapter_names") as default_mock, \
             patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament",
                   return_value=[_adapter_result(n, staging_root) for n in adapters]) as tournament_mock, \
             patch(f"{MOCK_BASE}.apply_paragraph_continuity_repair"), \
             patch(f"{MOCK_BASE}.apply_fix_extensions"), \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection) as selector_mock, \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result):
            run_full_tournament(
                source_path,
                staging_root,
                adapters=adapters,
                judge_settings=_judge_settings(),
                promote=False,
            )

        default_mock.assert_not_called()
        tournament_mock.assert_called_once_with(
            source_path,
            staging_root,
            adapters,
            timeout_s=600,
        )
        selector_mock.assert_called_once_with(
            source_path,
            staging_root,
            adapters,
            near_tie_threshold=NEAR_TIE_THRESHOLD,
        )

    def test_explicit_empty_adapter_list_is_preserved(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        staging_root = tmp_path / "staging"
        source_path.write_bytes(b"%PDF-1.4")
        selection = _selection()

        with patch(f"{MOCK_BASE}.default_adapter_names") as default_mock, \
             patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[]) as tournament_mock, \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection) as selector_mock:
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=[],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=False,
            )

        assert result.winner is None
        default_mock.assert_not_called()
        tournament_mock.assert_called_once_with(
            source_path,
            staging_root,
            [],
            timeout_s=600,
        )
        selector_mock.assert_called_once_with(
            source_path,
            staging_root,
            [],
            near_tie_threshold=NEAR_TIE_THRESHOLD,
        )

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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                tmp_path / "staging",
                judge_settings=_judge_settings(),
            )
        assert result.winner == "inhouse"
        assert result.judge_verdict is not None
        assert result.judge_verdict.preferred_adapter == "inhouse"
        assert result.audit_mode == AUDIT_MODE_AUTO

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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                tmp_path / "staging",
                judge_settings=_judge_settings(),
            )
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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                tmp_path / "staging",
                judge_settings=_judge_settings(),
            )
        assert result.winner is None
        assert result.escalated is True
        assert result.promoted is False

    def test_light_mode_skips_llm_audit(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        staging_root = tmp_path / "staging"
        source_path.write_bytes(b"%PDF-1.4")
        selection = _selection("inhouse", "docling")

        with patch(f"{MOCK_BASE}.default_adapter_names", return_value=["inhouse"]), \
             patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[]), \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection), \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop") as audit_mock:
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=None,
                audit_mode=AUDIT_MODE_LIGHT,
                promote=False,
            )

        audit_mock.assert_not_called()
        assert result.winner == "inhouse"
        assert result.judge_verdict is None
        assert result.audit_mode == AUDIT_MODE_LIGHT

    def test_stale_index_fixed_is_cleared_before_selection(self, tmp_path: Path) -> None:
        source_path = tmp_path / "doc.pdf"
        source_path.write_bytes(b"%PDF-1.4")
        staging_root = tmp_path / "staging"
        adapter_dir = staging_root / "inhouse"
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "index.md").write_text("# Fresh", encoding="utf-8")
        stale = adapter_dir / "index_fixed.md"
        stale.write_text("stale published output from a prior run", encoding="utf-8")
        selection = _selection("inhouse")
        audit_result = _audit_result(winner="inhouse", verdict=_verdict("inhouse"))

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament",
                   return_value=[_adapter_result("inhouse", staging_root, md="# Fresh")]), \
             patch(f"{MOCK_BASE}.select_candidate", return_value=selection), \
             patch(f"{MOCK_BASE}.run_post_selection_audit_loop", return_value=audit_result):
            run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse"],
                judge_settings=_judge_settings(),
                promote=False,
            )

        # No fix files exist, so apply_fix_extensions is a no-op; without the
        # Stage 2.3 guard the stale fixed output would survive into selection.
        assert not stale.exists()
        assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# Fresh"
        assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
        assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()

    def test_paragraph_repair_runs_before_selection_and_promotes_fixed(
        self,
        tmp_path: Path,
    ) -> None:
        source_path = tmp_path / "doc.txt"
        source_path.write_text("source content", encoding="utf-8")
        staging_root = tmp_path / "staging"
        raw_text = _row_sliced_fixture()
        adapter_result = _adapter_result("inhouse", staging_root, md=raw_text)
        selection = _selection("inhouse")

        def _select_after_repair(source, root, adapters, *, near_tie_threshold):
            adapter_dir = root / "inhouse"
            repaired = adapter_dir / PARAGRAPH_REPAIRED_MD
            fixed = adapter_dir / "index_fixed.md"
            assert paragraph_repair_candidate_is_current(adapter_dir) is True
            assert fixed.read_text(encoding="utf-8") == repaired.read_text(encoding="utf-8")
            assert fixed.read_text(encoding="utf-8") != raw_text
            assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text
            return selection

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[adapter_result]), \
             patch(f"{MOCK_BASE}.select_candidate", side_effect=_select_after_repair):
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse"],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=False,
            )

        assert result.winner == "inhouse"

    def test_paragraph_repair_off_clears_current_candidate_before_selection(
        self,
        tmp_path: Path,
    ) -> None:
        source_path = tmp_path / "doc.txt"
        source_path.write_text("source content", encoding="utf-8")
        staging_root = tmp_path / "staging"
        raw_text = _row_sliced_fixture()
        adapter_result = _adapter_result("inhouse", staging_root, md=raw_text)
        adapter_dir = staging_root / "inhouse"
        report = apply_paragraph_continuity_repair("inhouse", adapter_dir, source_path)
        assert report.accepted is True
        assert paragraph_repair_candidate_is_current(adapter_dir) is True
        (adapter_dir / "index_fixed.md").write_text("stale fixed output", encoding="utf-8")
        selection = _selection("inhouse")

        def _select_after_disabled_repair(source, root, adapters, *, near_tie_threshold):
            adapter_dir = root / "inhouse"
            assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
            assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
            assert not (adapter_dir / "index_fixed.md").exists()
            assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text
            return selection

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[adapter_result]), \
             patch(f"{MOCK_BASE}.select_candidate", side_effect=_select_after_disabled_repair):
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse"],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=False,
                paragraph_repair="off",
            )

        assert result.winner == "inhouse"

    def test_project_fix_extension_runs_after_paragraph_repair(
        self,
        tmp_path: Path,
    ) -> None:
        source_path = tmp_path / "doc.txt"
        source_path.write_text("source content", encoding="utf-8")
        staging_root = tmp_path / "staging"
        raw_text = _row_sliced_fixture()
        adapter_result = _adapter_result("inhouse", staging_root, md=raw_text)
        (staging_root / "fix_extension.py").write_text(
            "def apply_fix_extension(source_path, staging_dir, converter_name):\n"
            "    md = staging_dir / 'index.md'\n"
            "    md.write_text(md.read_text(encoding='utf-8') + ' APPENDED', encoding='utf-8')\n",
            encoding="utf-8",
        )
        selection = _selection("inhouse")
        scores = iter([10.0, 5.0])

        def _build_scorecard(_report, adapter_name):
            return _scorecard(adapter_name, next(scores, 5.0))

        def _select_after_fix(source, root, adapters, *, near_tie_threshold):
            adapter_dir = root / "inhouse"
            repaired_text = (adapter_dir / PARAGRAPH_REPAIRED_MD).read_text(
                encoding="utf-8"
            )
            fixed_text = (adapter_dir / "index_fixed.md").read_text(encoding="utf-8")
            assert fixed_text == repaired_text + " APPENDED"
            assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text
            return selection

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[adapter_result]), \
             patch("anydoc2md.fix_application.build_scorecard", side_effect=_build_scorecard), \
             patch(f"{MOCK_BASE}.select_candidate", side_effect=_select_after_fix):
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse"],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=False,
            )

        assert result.winner == "inhouse"

    def test_timed_out_adapter_late_write_is_not_selected_or_promoted(
        self,
        tmp_path: Path,
    ) -> None:
        # A timed-out adapter's worker thread can keep running after
        # run_tournament returns and write a late index.md into its staging dir.
        # Selection must key on AdapterResult.status, not on that resurrected
        # file, and publish only the genuinely-succeeded adapter.
        source_path = tmp_path / "doc.pdf"
        source_path.write_bytes(b"%PDF-1.4")
        staging_root = tmp_path / "staging"

        inhouse = _adapter_result("inhouse", staging_root, md="# Inhouse")

        docling_dir = staging_root / "docling"
        docling_dir.mkdir(parents=True, exist_ok=True)
        (docling_dir / "index.md").write_text(
            "# Late write from a timed-out worker", encoding="utf-8"
        )
        docling = AdapterResult(
            method_name="docling",
            method_version="1",
            command_invoked="",
            exit_code=-1,
            staging_dir=docling_dir,
            timing_ms=1,
            status="timeout",
            error_message="Adapter did not complete within wall-clock timeout",
        )

        captured: dict[str, list[str]] = {}

        def _capture_select(source, root, adapters, *, near_tie_threshold):
            captured["adapters"] = list(adapters)
            return _selection("inhouse")

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[inhouse, docling]), \
             patch(f"{MOCK_BASE}.apply_paragraph_continuity_repair") as repair_mock, \
             patch(f"{MOCK_BASE}.apply_fix_extensions") as fix_mock, \
             patch(f"{MOCK_BASE}.select_candidate", side_effect=_capture_select):
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse", "docling"],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=True,
            )

        # The timed-out adapter is never offered to selection...
        assert captured["adapters"] == ["inhouse"]
        # ...nor repaired/fixed, despite the late index.md on disk.
        repaired = [call.args[0] for call in repair_mock.call_args_list]
        fixed = [call.args[0] for call in fix_mock.call_args_list]
        assert "docling" not in repaired
        assert "docling" not in fixed
        # The published winner is the succeeded output, not the late write.
        assert result.winner == "inhouse"
        assert (
            (staging_root / WINNER_DIR_NAME / "index.md").read_text(encoding="utf-8")
            == "# Inhouse"
        )
        # Excluding the timed-out adapter from selection must not erase its
        # evidence from the serialized result.
        serialized = result.to_dict()
        docling_entry = next(
            entry for entry in serialized["adapter_results"]
            if entry["method_name"] == "docling"
        )
        assert docling_entry["status"] == "timeout"
        assert "wall-clock timeout" in docling_entry["error_message"]

    def test_all_timed_out_adapters_yield_no_winner_despite_on_disk_output(
        self,
        tmp_path: Path,
    ) -> None:
        source_path = tmp_path / "doc.pdf"
        source_path.write_bytes(b"%PDF-1.4")
        staging_root = tmp_path / "staging"

        adapter_dir = staging_root / "inhouse"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "index.md").write_text("# Late write", encoding="utf-8")
        timed_out = AdapterResult(
            method_name="inhouse",
            method_version="1",
            command_invoked="",
            exit_code=-1,
            staging_dir=adapter_dir,
            timing_ms=1,
            status="timeout",
            error_message="Adapter did not complete within wall-clock timeout",
        )

        captured: dict[str, list[str]] = {}

        def _capture_select(source, root, adapters, *, near_tie_threshold):
            captured["adapters"] = list(adapters)
            return _selection()  # no eligible adapters → no winner

        with patch(f"{MOCK_BASE}.classify", return_value=_traits()), \
             patch(f"{MOCK_BASE}.run_tournament", return_value=[timed_out]), \
             patch(f"{MOCK_BASE}.apply_paragraph_continuity_repair") as repair_mock, \
             patch(f"{MOCK_BASE}.apply_fix_extensions") as fix_mock, \
             patch(f"{MOCK_BASE}.select_candidate", side_effect=_capture_select):
            result = run_full_tournament(
                source_path,
                staging_root,
                adapters=["inhouse"],
                audit_mode=AUDIT_MODE_LIGHT,
                promote=True,
            )

        assert captured["adapters"] == []
        repair_mock.assert_not_called()
        fix_mock.assert_not_called()
        assert result.winner is None
        assert result.winner_staging_dir is None
        assert not (staging_root / WINNER_DIR_NAME).exists()


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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                staging,
                judge_settings=_judge_settings(),
            )

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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                staging,
                judge_settings=_judge_settings(),
                promote=False,
            )
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
            result = run_full_tournament(
                tmp_path / "doc.pdf",
                tmp_path / "staging",
                judge_settings=_judge_settings(),
            )
        assert result.winner is None
        assert result.winner_staging_dir is None
        assert result.promoted is False
