"""Shared document-to-Markdown conversion and QA helpers."""

from anydoc2md.llm_judge import JudgeVerdict, build_prompt, judge_near_tie

__all__ = [
    "JudgeVerdict",
    "build_prompt",
    "judge_near_tie",
]
