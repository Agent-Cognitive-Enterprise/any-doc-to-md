"""Agent-in-loop retry cycle for inhouse conversion quality improvement.

Implements the intended design:
  1. Convert (inhouse only)
  2. Score with hard gates and QA checks
  3. If quality is low and judge configured → judge → save findings
  4. Generate scaffolds (qa-extension + inhouse-extension) from findings
  5. Stage scaffolds and re-run — up to max_attempts times total
  6. If major issues persist after max_attempts → write escalation record

This is only meaningful when a judge is configured.  Without a judge,
run_full_tournament in light mode is the appropriate call.
"""
from __future__ import annotations

import datetime
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from anydoc2md.format_converters.tournament.orchestrator import (
    TournamentResult,
    run_full_tournament,
)
from anydoc2md.llm_judge import JudgeVerdict
from anydoc2md.remediation_authoring import author_project_local_scaffolds
from anydoc2md.settings import AUDIT_MODE_AUTO, JudgeSettings

MAX_LOOP_ATTEMPTS: int = 3
_MAJOR_SEVERITIES = frozenset({"critical", "major"})


@dataclass(frozen=True)
class LearningLoopResult:
    source_path: Path
    doc_key: str
    attempts: int
    escalated: bool
    escalation_path: Path | None
    final_result: TournamentResult
    scaffold_paths: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_path": str(self.source_path),
            "doc_key": self.doc_key,
            "attempts": self.attempts,
            "escalated": self.escalated,
            "escalation_path": str(self.escalation_path) if self.escalation_path else None,
            "scaffold_paths": [str(p) for p in self.scaffold_paths],
            "final_result": self.final_result.to_dict(),
        }


def run_learning_loop(
    source_path: Path,
    staging_root: Path,
    anydoc2md_dir: Path,
    doc_key: str,
    *,
    max_attempts: int = MAX_LOOP_ATTEMPTS,
    judge_settings: JudgeSettings | None = None,
    timeout_s: int = 600,
) -> LearningLoopResult:
    """Run the inhouse conversion + judge + scaffold-fix cycle, up to max_attempts.

    Each attempt:
      - Runs run_full_tournament with inhouse only and audit_mode=auto.
      - If the judge finds no major violations, accepts the result immediately.
      - If major violations are found, generates/updates scaffolds and stages them
        into staging_root so the next attempt picks them up via extension hooks.
    After max_attempts with persistent major findings, writes an escalation record.
    """
    scaffold_paths: list[Path] = []
    last_result: TournamentResult | None = None

    for attempt in range(1, max_attempts + 1):
        last_result = run_full_tournament(
            source_path,
            staging_root,
            adapters=["inhouse"],
            judge_settings=judge_settings,
            audit_mode=AUDIT_MODE_AUTO,
            timeout_s=timeout_s,
        )

        if not _has_major_findings(last_result.judge_verdict):
            return LearningLoopResult(
                source_path=source_path,
                doc_key=doc_key,
                attempts=attempt,
                escalated=False,
                escalation_path=None,
                final_result=last_result,
                scaffold_paths=scaffold_paths,
            )

        # Major findings — generate/update scaffolds
        if last_result.remediation_plan is not None:
            report_data = {"remediation_plan": last_result.remediation_plan.to_dict()}
            written = author_project_local_scaffolds(
                report_data=report_data,
                anydoc2md_dir=anydoc2md_dir,
                doc_key=doc_key,
                overwrite=True,
            )
            scaffold_paths.extend(written.values())
            _stage_scaffolds(written, staging_root)

    escalation_path = _write_escalation(
        anydoc2md_dir=anydoc2md_dir,
        doc_key=doc_key,
        source_path=source_path,
        attempts=max_attempts,
        final_result=last_result,
    )
    return LearningLoopResult(
        source_path=source_path,
        doc_key=doc_key,
        attempts=max_attempts,
        escalated=True,
        escalation_path=escalation_path,
        final_result=last_result,  # type: ignore[arg-type]
        scaffold_paths=scaffold_paths,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_major_findings(verdict: JudgeVerdict | None) -> bool:
    if verdict is None:
        return False
    return any(v.severity in _MAJOR_SEVERITIES for v in verdict.violations)


def _stage_scaffolds(written: dict[str, Path], staging_root: Path) -> None:
    """Copy generated scaffolds into staging_root so the extension loader picks them up."""
    name_map = {
        "qa_extension": "qa_extension.py",
        "inhouse_extension": "inhouse_extension.py",
    }
    for key, src_path in written.items():
        dest_name = name_map.get(key)
        if dest_name and src_path.exists():
            shutil.copy2(src_path, staging_root / dest_name)


def _write_escalation(
    *,
    anydoc2md_dir: Path,
    doc_key: str,
    source_path: Path,
    attempts: int,
    final_result: TournamentResult | None,
) -> Path:
    record = {
        "doc_key": doc_key,
        "source_path": str(source_path),
        "escalated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "attempts": attempts,
        "message": (
            f"Conversion quality issues persist after {attempts} attempt(s). "
            "Human review required."
        ),
        "final_winner": final_result.winner if final_result else None,
        "final_audit_mode": final_result.audit_mode if final_result else None,
        "violations": (
            [v.to_dict() for v in final_result.judge_verdict.violations]
            if final_result and final_result.judge_verdict
            else []
        ),
    }
    escalation_dir = anydoc2md_dir / "escalations"
    escalation_dir.mkdir(parents=True, exist_ok=True)
    path = escalation_dir / f"{doc_key}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=True), encoding="utf-8")
    return path
