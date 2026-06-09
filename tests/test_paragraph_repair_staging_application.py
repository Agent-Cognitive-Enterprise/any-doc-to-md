from __future__ import annotations

import hashlib
import json
from pathlib import Path

from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIRED_MD,
    PARAGRAPH_REPAIR_REPORT_JSON,
    apply_paragraph_continuity_repair,
)
from anydoc2md.paragraph_repair import application as repair_application
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings


def test_accepted_repair_writes_paragraph_artifact_and_sidecar(
    tmp_path: Path,
) -> None:
    original = _row_sliced_fixture()
    adapter_dir, source_path = _setup_staging(tmp_path, original)
    settings = ParagraphRepairSettings(max_examples=1, max_example_chars=12)

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
        settings=settings,
    )

    repaired_path = adapter_dir / PARAGRAPH_REPAIRED_MD
    sidecar_path = adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON
    repaired_text = repaired_path.read_text(encoding="utf-8")
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert report.accepted is True
    assert report.reason == "accepted"
    assert repaired_text != original
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == original
    assert not (adapter_dir / "index_fixed.md").exists()
    assert payload["schema_version"] == 1
    assert payload["created_by"] == "anydoc2md.paragraph_repair"
    assert payload["adapter_name"] == "inhouse"
    assert payload["source_document"] == {"path": source_path.name}
    assert payload["adapter_staging"] == {"path": ".", "name": adapter_dir.name}
    assert payload["owns_output"] is True
    assert payload["publishes_index_fixed"] is False
    assert payload["input"] == {
        "path": "index.md",
        "sha256": _sha256(original),
        "size_bytes": len(original.encode("utf-8")),
    }
    assert payload["output"] == {
        "path": PARAGRAPH_REPAIRED_MD,
        "sha256": _sha256(repaired_text),
        "size_bytes": len(repaired_text.encode("utf-8")),
    }
    assert payload["report"] == report.to_dict()
    assert len(payload["report"]["examples"]) <= 1
    assert all(len(example) <= 12 for example in payload["report"]["examples"])
    assert str(tmp_path) not in json.dumps(payload)


def test_accepted_repair_does_not_overwrite_unrelated_index_fixed(
    tmp_path: Path,
) -> None:
    adapter_dir, source_path = _setup_staging(tmp_path, _row_sliced_fixture())
    fixed_path = adapter_dir / "index_fixed.md"
    fixed_path.write_text("fix-extension output", encoding="utf-8")

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.accepted is True
    assert fixed_path.read_text(encoding="utf-8") == "fix-extension output"
    assert (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()


def test_rejected_repair_does_not_write_fixed_output_or_sidecar(
    tmp_path: Path,
) -> None:
    adapter_dir, source_path = _setup_staging(tmp_path, _normal_prose_fixture())

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.accepted is False
    assert report.reason == "no_merge_groups"
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


def test_missing_staging_dir_is_safe_noop(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "staging" / "inhouse"
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.attempted is False
    assert report.accepted is False
    assert report.reason == "staging_dir_missing"
    assert report.original_paragraph_count == 0
    assert not (adapter_dir / "index_fixed.md").exists()
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


def test_non_directory_staging_path_is_safe_noop(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "staging-file"
    adapter_dir.write_text("not a directory", encoding="utf-8")
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.attempted is False
    assert report.accepted is False
    assert report.reason == "staging_dir_missing"


def test_missing_index_md_is_safe_noop_and_clears_owned_outputs(
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "staging" / "inhouse"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / PARAGRAPH_REPAIRED_MD).write_text("stale", encoding="utf-8")
    (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).write_text(
        '{"stale": true}',
        encoding="utf-8",
    )
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.attempted is False
    assert report.accepted is False
    assert report.reason == "index_md_missing"
    assert report.original_paragraph_count == 0
    assert not (adapter_dir / "index_fixed.md").exists()
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


def test_rejected_repair_preserves_index_fixed_and_clears_owned_outputs(
    tmp_path: Path,
) -> None:
    adapter_dir, source_path = _setup_staging(tmp_path, _normal_prose_fixture())
    fixed_path = adapter_dir / "index_fixed.md"
    fixed_path.write_text("unrelated fixed output", encoding="utf-8")
    (adapter_dir / PARAGRAPH_REPAIRED_MD).write_text("stale", encoding="utf-8")
    (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).write_text(
        '{"stale": true}',
        encoding="utf-8",
    )

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
    )

    assert report.accepted is False
    assert fixed_path.read_text(encoding="utf-8") == "unrelated fixed output"
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


def test_disabled_repair_clears_owned_outputs_without_touching_index_fixed(
    tmp_path: Path,
) -> None:
    adapter_dir, source_path = _setup_staging(tmp_path, _row_sliced_fixture())
    fixed_path = adapter_dir / "index_fixed.md"
    fixed_path.write_text("fix-extension output", encoding="utf-8")
    (adapter_dir / PARAGRAPH_REPAIRED_MD).write_text("stale", encoding="utf-8")
    (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).write_text(
        '{"stale": true}',
        encoding="utf-8",
    )

    report = apply_paragraph_continuity_repair(
        "inhouse",
        adapter_dir,
        source_path,
        settings=ParagraphRepairSettings(enabled=False),
    )

    assert report.attempted is False
    assert report.accepted is False
    assert report.reason == "disabled"
    assert report.merge_group_count == 0
    assert fixed_path.read_text(encoding="utf-8") == "fix-extension output"
    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()


def test_atomic_write_cleans_temp_file_when_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tmp_path_for_write = tmp_path / ".index_paragraph_repaired.md.fail.tmp"

    class FailingTempFile:
        name = str(tmp_path_for_write)

        def __enter__(self):
            tmp_path_for_write.write_text("partial", encoding="utf-8")
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, _text):
            raise OSError("simulated disk full")

    def fake_named_temp_file(*_args, **_kwargs):
        return FailingTempFile()

    monkeypatch.setattr(
        repair_application,
        "NamedTemporaryFile",
        fake_named_temp_file,
    )

    target = tmp_path / PARAGRAPH_REPAIRED_MD
    try:
        repair_application._write_text_atomic(target, "content")
    except OSError as exc:
        assert str(exc) == "simulated disk full"
    else:
        raise AssertionError("expected write failure")

    assert not tmp_path_for_write.exists()
    assert not target.exists()


def test_package_exports_staging_helper() -> None:
    import anydoc2md.paragraph_repair as paragraph_repair

    assert (
        paragraph_repair.apply_paragraph_continuity_repair
        is apply_paragraph_continuity_repair
    )


def _setup_staging(tmp_path: Path, md_text: str) -> tuple[Path, Path]:
    adapter_dir = tmp_path / "staging" / "inhouse"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "index.md").write_text(md_text, encoding="utf-8")
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")
    return adapter_dir, source_path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _normal_prose_fixture() -> str:
    rows = [
        "The pump started after the alarm and stabilized within five minutes.",
        "The operator reviewed the sensor logs and found no missing readings.",
        "The maintenance lead scheduled a follow up inspection for the morning.",
        "The final note records that the intake remained open during the test.",
    ]
    return "\n\n".join(rows) + "\n"
