from __future__ import annotations

from pathlib import Path

from anydoc2md.paragraph_repair.application import (
    PARAGRAPH_REPAIR_REPORT_JSON,
    PARAGRAPH_REPAIRED_MD,
    apply_paragraph_continuity_repair,
)
from anydoc2md.staging_hygiene import (
    INDEX_FIXED_MD,
    prepare_adapter_fixed_output_slot,
)


def test_removes_stale_index_fixed_md(tmp_path: Path) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw adapter output\n")
    fixed = adapter_dir / INDEX_FIXED_MD
    fixed.write_text("stale published output\n", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not fixed.exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "raw adapter output\n"


def test_clean_dir_is_noop(tmp_path: Path) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw\n")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "raw\n"
    assert not (adapter_dir / INDEX_FIXED_MD).exists()


def test_missing_dir_is_noop(tmp_path: Path) -> None:
    missing = tmp_path / "staging" / "inhouse"

    prepare_adapter_fixed_output_slot(missing)

    assert not missing.exists()


def test_preserves_current_repair_candidate_and_removes_stale_fixed(
    tmp_path: Path,
) -> None:
    adapter_dir = _accepted_candidate_dir(tmp_path)
    fixed = adapter_dir / INDEX_FIXED_MD
    fixed.write_text("stale published output\n", encoding="utf-8")
    repaired_before = (adapter_dir / PARAGRAPH_REPAIRED_MD).read_text(encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not fixed.exists()
    assert (adapter_dir / PARAGRAPH_REPAIRED_MD).read_text(encoding="utf-8") == repaired_before
    assert (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
    assert (adapter_dir / "index.md").exists()


def test_removes_repair_candidate_when_index_changed(tmp_path: Path) -> None:
    adapter_dir = _accepted_candidate_dir(tmp_path)
    (adapter_dir / "index.md").write_text("regenerated raw output\n", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert not (adapter_dir / PARAGRAPH_REPAIR_REPORT_JSON).exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "regenerated raw output\n"


def test_removes_orphan_repaired_without_sidecar(tmp_path: Path) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw\n")
    (adapter_dir / PARAGRAPH_REPAIRED_MD).write_text("orphan repaired\n", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not (adapter_dir / PARAGRAPH_REPAIRED_MD).exists()
    assert (adapter_dir / "index.md").exists()


def test_preserves_unrelated_outputs(tmp_path: Path) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw\n")
    (adapter_dir / INDEX_FIXED_MD).write_text("stale\n", encoding="utf-8")
    images = adapter_dir / "images"
    images.mkdir()
    (images / "diagram.png").write_bytes(b"\x89PNG fake")
    (adapter_dir / "result.json").write_text('{"adapter": "inhouse"}', encoding="utf-8")
    (adapter_dir / "notes.txt").write_text("keep me", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not (adapter_dir / INDEX_FIXED_MD).exists()
    assert (images / "diagram.png").read_bytes() == b"\x89PNG fake"
    assert (adapter_dir / "result.json").exists()
    assert (adapter_dir / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (adapter_dir / "index.md").exists()


def test_only_touches_target_dir(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    adapter_a = _staging_dir(staging_root, "raw a\n", name="adapter_a")
    adapter_b = _staging_dir(staging_root, "raw b\n", name="adapter_b")
    (adapter_a / INDEX_FIXED_MD).write_text("stale a\n", encoding="utf-8")
    (adapter_b / INDEX_FIXED_MD).write_text("stale b\n", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_a)

    assert not (adapter_a / INDEX_FIXED_MD).exists()
    assert (adapter_b / INDEX_FIXED_MD).read_text(encoding="utf-8") == "stale b\n"


def test_removes_directory_named_index_fixed(tmp_path: Path) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw\n")
    fixed_dir = adapter_dir / INDEX_FIXED_MD
    fixed_dir.mkdir()
    (fixed_dir / "nested.txt").write_text("junk", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not fixed_dir.exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "raw\n"


def test_removes_symlink_named_index_fixed_without_touching_target(
    tmp_path: Path,
) -> None:
    adapter_dir = _staging_dir(tmp_path, "raw\n")
    target = tmp_path / "real_target.md"
    target.write_text("important external content\n", encoding="utf-8")
    link = adapter_dir / INDEX_FIXED_MD
    link.symlink_to(target)

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not link.exists()
    assert target.read_text(encoding="utf-8") == "important external content\n"


def test_removes_index_fixed_without_index_md(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "staging" / "inhouse"
    adapter_dir.mkdir(parents=True)
    fixed = adapter_dir / INDEX_FIXED_MD
    fixed.write_text("stale published output\n", encoding="utf-8")

    prepare_adapter_fixed_output_slot(adapter_dir)

    assert not fixed.exists()


def _staging_dir(parent: Path, md_text: str, *, name: str = "inhouse") -> Path:
    adapter_dir = parent / name
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / "index.md").write_text(md_text, encoding="utf-8")
    return adapter_dir


def _accepted_candidate_dir(tmp_path: Path) -> Path:
    adapter_dir = tmp_path / "staging" / "inhouse"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "index.md").write_text(_row_sliced_fixture(), encoding="utf-8")
    source_path = tmp_path / "source.txt"
    source_path.write_text("source content", encoding="utf-8")
    report = apply_paragraph_continuity_repair("inhouse", adapter_dir, source_path)
    assert report.accepted is True
    return adapter_dir


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
