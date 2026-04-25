from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.classification.classify_document import DocumentTraits
from anydoc2md.settings import JudgeSettings


def adapter_result(name: str, staging_dir: Path, md: str) -> AdapterResult:
    staging = staging_dir / name
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


def traits(**kwargs) -> DocumentTraits:
    defaults = dict(
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
    defaults.update(kwargs)
    return DocumentTraits(**defaults)


def mock_response(
    preferred: str,
    confidence: str = "high",
    reasoning: str = "Good.",
) -> MagicMock:
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "preferred": preferred,
                                "confidence": confidence,
                                "reasoning": reasoning,
                                "notes": {preferred: "Best output."},
                                "violations": [
                                    {
                                        "type": "reading_order",
                                        "severity": "major",
                                        "count": 1,
                                        "pages": [2],
                                        "confidence": 0.91,
                                        "evidence": "Paragraphs are out of order.",
                                        "root_cause": "multicolumn merge",
                                    }
                                ],
                                "overall_confidence": 0.87,
                                "uncertainty_note": "",
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 512},
        }
    )
    mock = MagicMock()
    mock.json.return_value = json.loads(body)
    mock.raise_for_status = MagicMock()
    return mock


def judge_settings(
    url: str = "http://localhost:1234/v1",
    model: str = "qwen/qwen3.6-35b-a3b",
) -> JudgeSettings:
    return JudgeSettings(url=url, model=model)
