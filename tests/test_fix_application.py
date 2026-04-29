from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from anydoc2md.fix_application import _find_fix_files, apply_fix_extensions
from anydoc2md.output_qa.scoring import ScoreCard


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


def test_no_index_md_noop(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    adapter_dir = staging_root / "inhouse"
    adapter_dir.mkdir(parents=True)
    source = tmp_path / "doc.txt"
    source.write_text("x", encoding="utf-8")
    _write_fix(staging_root, "fix_extension.py", _FIX_UPPERCASE)
    apply_fix_extensions("inhouse", adapter_dir, staging_root, source)
    assert not (adapter_dir / "index_fixed.md").exists()


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
