from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from anydoc2md.fix_application import _find_fix_files, apply_fix_extensions
from anydoc2md.output_qa.scoring import ScoreCard
from anydoc2md.paragraph_repair.application import (
    apply_paragraph_continuity_repair,
    paragraph_repair_candidate_is_current,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scorecard(name: str, score: float) -> ScoreCard:
    return ScoreCard(name, score, {}, 0, 0, 1)


def _write_fix(staging_root: Path, filename: str, body: str) -> Path:
    p = staging_root / filename
    p.write_text(body, encoding="utf-8")
    return p


_FIX_UPPERCASE = """\
def apply_fix_extension(src, staging, conv):
    md = staging / 'index.md'
    md.write_text(md.read_text(encoding='utf-8').upper(), encoding='utf-8')
"""

_FIX_APPEND = """\
def apply_fix_extension(src, staging, conv):
    md = staging / 'index.md'
    md.write_text(md.read_text(encoding='utf-8') + ' APPENDED', encoding='utf-8')
"""

_FIX_NOOP = """\
def apply_fix_extension(src, staging, conv):
    pass
"""

_FIX_RAISES = """\
def apply_fix_extension(src, staging, conv):
    raise RuntimeError("intentional failure")
"""


def _setup(tmp_path: Path, content: str = "# original") -> tuple[Path, Path, Path]:
    staging_root = tmp_path / "staging"
    adapter_dir = staging_root / "inhouse"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "index.md").write_text(content, encoding="utf-8")
    source = tmp_path / "doc.txt"
    source.write_text("source content", encoding="utf-8")
    return staging_root, adapter_dir, source


def _patch_scores(*scores: float):
    """Return a patch ctx that returns ScoreCards with the given scores in order."""
    call_count = [0]

    def _side(report, name):
        s = scores[min(call_count[0], len(scores) - 1)]
        call_count[0] += 1
        return _make_scorecard(name, s)

    return patch("anydoc2md.fix_application.build_scorecard", side_effect=_side)


# ---------------------------------------------------------------------------
# _find_fix_files
# ---------------------------------------------------------------------------

def test_find_fix_files_empty_dir(tmp_path: Path) -> None:
    assert _find_fix_files(tmp_path) == []


def test_find_fix_files_merged_only(tmp_path: Path) -> None:
    merged = tmp_path / "fix_extension.py"
    merged.write_text("", encoding="utf-8")
    assert _find_fix_files(tmp_path) == [merged]


def test_find_fix_files_prefers_components_over_merged(tmp_path: Path) -> None:
    (tmp_path / "fix_extension.py").write_text("", encoding="utf-8")
    c0 = tmp_path / "_all_fix_0.py"
    c1 = tmp_path / "_all_fix_1.py"
    c0.write_text("", encoding="utf-8")
    c1.write_text("", encoding="utf-8")
    result = _find_fix_files(tmp_path)
    assert result == [c0, c1]


# ---------------------------------------------------------------------------
# apply_fix_extensions — no-op cases
# ---------------------------------------------------------------------------

def test_no_fix_files_no_index_fixed(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)
    assert not (adapter_dir / "index_fixed.md").exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


@pytest.mark.parametrize("kind", ["file", "dir", "symlink"])
def test_no_fix_files_clears_stale_index_fixed_any_type(tmp_path: Path, kind: str) -> None:
    # No fix files and no trusted repair candidate: this function owns
    # index_fixed.md, so a stale prior-run slot must not survive, regardless of
    # whether it is a file, a directory, or a symlink.
    staging_root, adapter_dir, source = _setup(tmp_path)
    fixed = adapter_dir / "index_fixed.md"
    if kind == "file":
        fixed.write_text("stale", encoding="utf-8")
    elif kind == "dir":
        fixed.mkdir()
        (fixed / "leftover.txt").write_text("x", encoding="utf-8")
    else:  # symlink
        target = adapter_dir / "elsewhere.md"
        target.write_text("target", encoding="utf-8")
        fixed.symlink_to(target)

    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not fixed.exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"
    if kind == "symlink":
        # The symlink is unlinked without following it; the target is untouched.
        assert (adapter_dir / "elsewhere.md").read_text(encoding="utf-8") == "target"


def test_stale_dir_slot_does_not_block_fix_write(tmp_path: Path) -> None:
    # An improving fix must write index_fixed.md even if a stale directory
    # occupies the slot — the write path must clear the slot type-agnostically.
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)
    fixed = adapter_dir / "index_fixed.md"
    fixed.mkdir()
    (fixed / "leftover.txt").write_text("x", encoding="utf-8")

    with _patch_scores(10.0, 5.0):  # fix improves → must write index_fixed.md
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert fixed.is_file()
    assert fixed.read_text(encoding="utf-8") == "# ORIGINAL"
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


def test_no_index_md_noop(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    adapter_dir = staging_root / "inhouse"
    adapter_dir.mkdir(parents=True)
    source = tmp_path / "doc.txt"
    source.write_text("x", encoding="utf-8")
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)
    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)
    assert not (adapter_dir / "index_fixed.md").exists()


@pytest.mark.parametrize("kind", ["file", "dir", "symlink"])
def test_no_index_md_clears_stale_index_fixed_any_type(
    tmp_path: Path,
    kind: str,
) -> None:
    staging_root = tmp_path / "staging"
    adapter_dir = staging_root / "inhouse"
    adapter_dir.mkdir(parents=True)
    fixed = adapter_dir / "index_fixed.md"
    if kind == "file":
        fixed.write_text("stale", encoding="utf-8")
    elif kind == "dir":
        fixed.mkdir()
        (fixed / "leftover.txt").write_text("x", encoding="utf-8")
    else:  # symlink
        target = adapter_dir / "elsewhere.md"
        target.write_text("target", encoding="utf-8")
        fixed.symlink_to(target)
    source = tmp_path / "doc.txt"
    source.write_text("x", encoding="utf-8")
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)

    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not fixed.exists()
    if kind == "symlink":
        assert (adapter_dir / "elsewhere.md").read_text(encoding="utf-8") == "target"


# ---------------------------------------------------------------------------
# apply_fix_extensions — score-based keep/discard
# ---------------------------------------------------------------------------

def test_fix_that_improves_score_writes_index_fixed(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)

    with _patch_scores(10.0, 5.0):  # base=10, candidate=5 → keep
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == "# ORIGINAL"
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


def test_fix_with_equal_score_discarded(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)

    with _patch_scores(10.0, 10.0):  # equal → discard
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not (adapter_dir / "index_fixed.md").exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


def test_fix_that_worsens_score_discarded(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)

    with _patch_scores(5.0, 10.0):  # worse → discard
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not (adapter_dir / "index_fixed.md").exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


def test_stale_index_fixed_removed_when_no_improvement(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)
    (adapter_dir / "index_fixed.md").write_text("stale", encoding="utf-8")

    with _patch_scores(5.0, 10.0):  # worse → discard
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not (adapter_dir / "index_fixed.md").exists()


# ---------------------------------------------------------------------------
# apply_fix_extensions — multiple fix files
# ---------------------------------------------------------------------------

def test_multiple_fixes_both_improving_accumulate(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path, "hello")
    c0 = _write_fix(staging_root, "_all_fix_0.py", _FIX_UPPERCASE)
    c1 = _write_fix(staging_root, "_all_fix_1.py", _FIX_APPEND)

    with _patch_scores(10.0, 7.0, 4.0):  # base, after c0, after c1 → both kept
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    result = (adapter_dir / "index_fixed.md").read_text(encoding="utf-8")
    assert result == "HELLO APPENDED"
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "hello"


def test_second_fix_rejected_when_worse_than_first_not_just_original(tmp_path: Path) -> None:
    # Regression: guard must compare against current_score, not base_score.
    # fix_1: 10→5 accepted; fix_2: →8, which beats original (8<10) but loses to fix_1 (8>5)
    # → fix_2 must be rejected; index_fixed.md must contain fix_1's output only.
    staging_root, adapter_dir, source = _setup(tmp_path, "hello")
    _write_fix(staging_root, "_all_fix_0.py", _FIX_UPPERCASE)  # accepted: "HELLO"
    _write_fix(staging_root, "_all_fix_1.py", _FIX_APPEND)     # rejected: "HELLO APPENDED"

    with _patch_scores(10.0, 5.0, 8.0):  # base=10, after fix_1=5 (keep), after fix_2=8 (reject)
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == "HELLO"
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "hello"


def test_multiple_fixes_first_bad_second_good(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path, "hello")
    _write_fix(staging_root, "_all_fix_0.py", _FIX_NOOP)    # no change → equal → discard
    _write_fix(staging_root, "_all_fix_1.py", _FIX_UPPERCASE)  # improves

    with _patch_scores(10.0, 10.0, 5.0):  # base, c0 equal → discard, c1 better → keep
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == "HELLO"


# ---------------------------------------------------------------------------
# apply_fix_extensions — error handling
# ---------------------------------------------------------------------------

def test_fix_that_raises_is_skipped(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_RAISES)

    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not (adapter_dir / "index_fixed.md").exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


def test_fix_missing_hook_is_skipped(tmp_path: Path) -> None:
    staging_root, adapter_dir, source = _setup(tmp_path)
    _write_fix(staging_root, "fix_extension.py", "# no hook defined\n")

    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert not (adapter_dir / "index_fixed.md").exists()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == "# original"


# ---------------------------------------------------------------------------
# apply_fix_extensions — trusted paragraph-repair candidate as base (Slice 9)
# ---------------------------------------------------------------------------

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


def _make_trusted_candidate(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    """Stage an adapter dir with a real, trusted current-run repair candidate.

    Returns (staging_root, adapter_dir, source, raw_text, repaired_text).
    """
    staging_root = tmp_path / "staging"
    adapter_dir = staging_root / "inhouse"
    adapter_dir.mkdir(parents=True)
    raw_text = _row_sliced_fixture()
    (adapter_dir / "index.md").write_text(raw_text, encoding="utf-8")
    source = tmp_path / "doc.txt"
    source.write_text("source content", encoding="utf-8")

    report = apply_paragraph_continuity_repair("inhouse", adapter_dir, source)
    assert report.accepted is True
    assert paragraph_repair_candidate_is_current(adapter_dir) is True
    repaired_text = (adapter_dir / "index_paragraph_repaired.md").read_text(encoding="utf-8")
    assert repaired_text != raw_text  # repair actually changed something
    return staging_root, adapter_dir, source, raw_text, repaired_text


def test_trusted_candidate_no_fix_files_promotes_repaired(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, repaired_text = _make_trusted_candidate(tmp_path)

    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == repaired_text
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text


def test_trusted_candidate_non_improving_fix_keeps_repaired_base(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, repaired_text = _make_trusted_candidate(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_APPEND)

    with _patch_scores(5.0, 10.0):  # base(repaired)=5, after fix=10 (worse) → reject fix
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    # Built-in repair is still promoted even though the project-local fix lost.
    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == repaired_text
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text


def test_trusted_candidate_improving_fix_builds_on_repaired(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, repaired_text = _make_trusted_candidate(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_APPEND)

    with _patch_scores(10.0, 5.0):  # base(repaired)=10, after fix=5 (better) → keep
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    # The fix appended to the *repaired* text, proving it built on the candidate.
    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == repaired_text + " APPENDED"
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text


def test_untrusted_candidate_not_used_as_base(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, _ = _make_trusted_candidate(tmp_path)
    # Make the candidate untrusted by forging the sidecar owner.
    sidecar = adapter_dir / "paragraph_repair_report.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["created_by"] = "some.other.tool"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    assert paragraph_repair_candidate_is_current(adapter_dir) is False

    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)
    with _patch_scores(10.0, 5.0):  # base=10, after fix=5 → keep
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    # Base was the raw index.md, not the (untrusted) repaired text.
    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == raw_text.upper()
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text


def test_trusted_candidate_fix_raises_promotes_repaired_and_restores_index(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, repaired_text = _make_trusted_candidate(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_RAISES)

    with _patch_scores(10.0):  # only the base is scored; the raising fix never is
        apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    assert (adapter_dir / "index_fixed.md").read_text(encoding="utf-8") == repaired_text
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text


def test_trusted_candidate_base_scoring_error_restores_raw_index(tmp_path: Path) -> None:
    staging_root, adapter_dir, source, raw_text, _ = _make_trusted_candidate(tmp_path)
    _write_fix(staging_root, "fix_extension.py", _FIX_APPEND)

    # Base scoring raises while the repaired base is staged in index.md.
    with patch("anydoc2md.fix_application.build_scorecard", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            apply_fix_extensions("inhouse", adapter_dir, staging_root, source)

    # Raw adapter output is still restored despite the mid-flight failure.
    assert (adapter_dir / "index.md").read_text(encoding="utf-8") == raw_text
