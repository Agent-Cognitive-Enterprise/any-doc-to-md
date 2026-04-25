from __future__ import annotations

from pathlib import Path

from anydoc2md.format_converters.adapters import inhouse
from anydoc2md.format_converters.base import load_overrides
from anydoc2md.output_qa.runner import run_all


def test_qa_extension_from_adapter_staging_dir_is_not_executed(tmp_path: Path) -> None:
    staging = tmp_path / "doc" / "inhouse"
    staging.mkdir(parents=True)
    (staging / "index.md").write_text("- • bad bullet\n", encoding="utf-8")
    (staging / "qa_extension.py").write_text(
        """
from anydoc2md.output_qa.checks import CheckResult

def get_disabled_checks():
    return ["check_no_double_bullets"]

def get_additional_md_only_checks():
    def custom_check(md_text):
        return CheckResult("staging_extension_executed", 1, "fail", "Should not run.")
    return [custom_check]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = run_all(staging)

    check_names = [check.name for check in report.checks]
    assert "no_double_bullets" in check_names
    assert "staging_extension_executed" not in check_names


def test_inhouse_extension_from_adapter_staging_dir_is_not_executed(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Safe text.", encoding="utf-8")
    staging = tmp_path / "doc" / "inhouse"
    staging.mkdir(parents=True)
    (staging / "inhouse_extension.py").write_text(
        """
def apply_inhouse_extension(source_path, staging_dir, converter_name):
    raise RuntimeError("staging extension should not run")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = inhouse.run(source, staging)

    assert result.succeeded
    assert "Safe text." in result.markdown_text


def test_override_files_can_still_be_loaded_from_adapter_staging_dir(tmp_path: Path) -> None:
    staging = tmp_path / "doc" / "inhouse"
    staging.mkdir(parents=True)
    (staging / "document.override.yaml").write_text("min_text_len: 22\n", encoding="utf-8")

    assert load_overrides(staging)["min_text_len"] == 22
