"""Shared document-to-Markdown conversion and QA helpers."""

from anydoc2md.llm_judge import (
    JudgeVerdict,
    build_audit_prompt,
    build_prompt,
    judge_candidate_against_source,
    judge_near_tie,
)
from anydoc2md.remediation_authoring import author_project_local_scaffolds
from anydoc2md.settings import (
    AUDIT_MODE_AUTO,
    AUDIT_MODE_LIGHT,
    AnyDocToMdConfigError,
    JudgeSettings,
    PARAGRAPH_REPAIR_AUTO,
    PARAGRAPH_REPAIR_OFF,
    load_judge_settings_from_env,
    normalize_audit_mode,
    normalize_paragraph_repair_mode,
)

__all__ = [
    "AUDIT_MODE_AUTO",
    "AUDIT_MODE_LIGHT",
    "AnyDocToMdConfigError",
    "JudgeVerdict",
    "JudgeSettings",
    "PARAGRAPH_REPAIR_AUTO",
    "PARAGRAPH_REPAIR_OFF",
    "author_project_local_scaffolds",
    "build_audit_prompt",
    "build_prompt",
    "judge_candidate_against_source",
    "judge_near_tie",
    "load_judge_settings_from_env",
    "normalize_audit_mode",
    "normalize_paragraph_repair_mode",
]
