"""
QA runner — executes all checks and produces a QAReport.

Usage (CLI):
    python -m anydoc2md.output_qa.runner <staging_dir> [source_file]

JSON report is written to stdout; exit code 1 on any failure.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from anydoc2md.output_qa.checks import (
    CheckResult,
    check_box_title_precedes_content,
    check_caption_near_image,
    check_image_count_match,
    check_image_size_plausible,
    check_images_locally_resolvable,
    check_no_double_bullets,
    check_no_repeated_headings,
    check_numbered_list_sequential,
    check_heading_not_fragmented,
    check_text_coverage,
)

_LAYER1_CHECKS_MD_ONLY = [
    check_no_double_bullets,
    check_numbered_list_sequential,
    check_heading_not_fragmented,
    check_caption_near_image,
    check_box_title_precedes_content,
    check_image_size_plausible,
    check_no_repeated_headings,
]

# Takes (md_text, staging_dir)
_LAYER1_CHECKS_WITH_DIR = [
    check_images_locally_resolvable,
]

# Takes (md_text, source_path)
_LAYER2_CHECKS = [
    check_image_count_match,
    check_text_coverage,
]


@dataclass
class QAReport:
    staging_dir: str
    source: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.status != "fail" for c in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warned(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == "warn"]

    def to_dict(self) -> dict:
        return {
            "staging_dir": self.staging_dir,
            "source": self.source,
            "passed": self.passed,
            "summary": {
                "pass": sum(1 for c in self.checks if c.status == "pass"),
                "warn": sum(1 for c in self.checks if c.status == "warn"),
                "fail": sum(1 for c in self.checks if c.status == "fail"),
            },
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def run_all(
    staging_dir: Path,
    source_path: Path | None = None,
) -> QAReport:
    """
    Run all applicable QA checks.

    Layer 1 checks always run (index.md + staging_dir).
    Layer 2 checks run only when source_path is provided.
    """
    index_md = staging_dir / "index.md"
    if not index_md.exists():
        raise FileNotFoundError(f"index.md not found in {staging_dir}")

    md_text = index_md.read_text(encoding="utf-8")
    results: list[CheckResult] = []

    for fn in _LAYER1_CHECKS_MD_ONLY:
        results.append(fn(md_text))

    for fn in _LAYER1_CHECKS_WITH_DIR:
        results.append(fn(md_text, staging_dir))

    if source_path is not None:
        for fn in _LAYER2_CHECKS:
            results.append(fn(md_text, source_path))

    return QAReport(
        staging_dir=str(staging_dir),
        source=str(source_path) if source_path else "",
        checks=results,
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m anydoc2md.output_qa.runner <staging_dir> [source_file]",
              file=sys.stderr)
        sys.exit(1)

    staging_dir = Path(sys.argv[1])
    source_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    report = run_all(staging_dir, source_path)
    print(report.to_json())
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
