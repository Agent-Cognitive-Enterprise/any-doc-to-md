"""
Tests for output_qa/hard_gates.py.

All tests use in-memory content or temp files — no PDF toolchain required.
Layer 2 gate (text_coverage_minimum) is tested via mocking fitz.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anydoc2md.output_qa.hard_gates import (
    HardGateResult,
    disqualified,
    first_failure,
    gate_charset_plausible,
    gate_index_md_exists,
    gate_no_broken_image_refs,
    gate_not_empty,
    gate_text_coverage_minimum,
    run_hard_gates,
    MIN_MARKDOWN_CHARS,
    MIN_PRINTABLE_RATIO,
    MIN_WORD_COVERAGE,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _staging(tmp_path: Path, md: str | None = "# Hello\n\nSome content here.") -> Path:
    d = tmp_path / "staging"
    d.mkdir()
    (d / "images").mkdir()
    if md is not None:
        (d / "index.md").write_text(md, encoding="utf-8")
    return d


def _write_png(path: Path, width: int = 10, height: int = 10) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\x00\x00\x00" * width
    idat_data = zlib.compress(scanline * height)

    def chunk(tag: bytes, data: bytes) -> bytes:
        import zlib as _zlib
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", _zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat_data)
        + chunk(b"IEND", b"")
    )


# =========================================================================== #
# HardGateResult contract
# =========================================================================== #

class TestHardGateResult:
    def test_to_dict_keys(self) -> None:
        r = HardGateResult("my_gate", True)
        d = r.to_dict()
        assert set(d) == {"gate_name", "passed", "reason"}

    def test_passed_has_empty_reason(self) -> None:
        r = HardGateResult("g", True)
        assert r.reason == ""

    def test_failed_has_reason(self) -> None:
        r = HardGateResult("g", False, "Something broke.")
        assert r.reason == "Something broke."


# =========================================================================== #
# gate_index_md_exists
# =========================================================================== #

class TestGateIndexMdExists:
    def test_pass_when_exists(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        assert gate_index_md_exists(d).passed is True

    def test_fail_when_missing(self, tmp_path: Path) -> None:
        d = _staging(tmp_path, md=None)
        r = gate_index_md_exists(d)
        assert r.passed is False
        assert "index.md" in r.reason


# =========================================================================== #
# gate_not_empty
# =========================================================================== #

class TestGateNotEmpty:
    def test_pass_above_threshold(self) -> None:
        assert gate_not_empty("x" * MIN_MARKDOWN_CHARS).passed is True

    def test_fail_below_threshold(self) -> None:
        r = gate_not_empty("hi")
        assert r.passed is False
        assert "short" in r.reason.lower()

    def test_pass_at_exact_threshold(self) -> None:
        assert gate_not_empty("x" * MIN_MARKDOWN_CHARS).passed is True

    def test_custom_min_chars(self) -> None:
        assert gate_not_empty("hello", min_chars=3).passed is True
        assert gate_not_empty("hi", min_chars=3).passed is False

    def test_whitespace_only_fails(self) -> None:
        assert gate_not_empty("   \n\n\t  ", min_chars=1).passed is False


# =========================================================================== #
# gate_no_broken_image_refs
# =========================================================================== #

class TestGateNoBrokenImageRefs:
    def test_pass_when_no_img_tags(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        r = gate_no_broken_image_refs("No images here.", d)
        assert r.passed is True

    def test_pass_when_all_refs_exist(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        _write_png(d / "images" / "fig.png")
        md = '<img src="images/fig.png" alt="x" width="10" height="10">'
        assert gate_no_broken_image_refs(md, d).passed is True

    def test_fail_when_ref_missing(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        md = '<img src="images/missing.png" alt="x" width="10" height="10">'
        r = gate_no_broken_image_refs(md, d)
        assert r.passed is False
        assert "missing.png" in r.reason

    def test_reason_truncates_at_3_missing(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        md = "".join(
            f'<img src="images/x{i}.png" alt="" width="1" height="1">'
            for i in range(5)
        )
        r = gate_no_broken_image_refs(md, d)
        assert r.passed is False
        assert "…" in r.reason


# =========================================================================== #
# gate_charset_plausible
# =========================================================================== #

class TestGateCharsetPlausible:
    def test_pass_normal_text(self) -> None:
        assert gate_charset_plausible("Hello world! " * 20).passed is True

    def test_fail_binary_garbage(self) -> None:
        garbage = bytes(range(0, 32)).decode("latin-1") * 20
        r = gate_charset_plausible(garbage)
        assert r.passed is False
        assert "%" in r.reason

    def test_skip_short_documents(self) -> None:
        # Short doc with garbage chars — gate should skip (pass)
        r = gate_charset_plausible(bytes(range(0, 32)).decode("latin-1"))
        assert r.passed is True
        assert "skipped" in r.reason.lower()

    def test_custom_min_ratio(self) -> None:
        # 50% printable
        text = "abc\x00\x01\x02" * 100
        assert gate_charset_plausible(text, min_ratio=0.3).passed is True
        assert gate_charset_plausible(text, min_ratio=0.9).passed is False

    def test_unicode_content_passes(self) -> None:
        # Unicode chars aren't in printable ASCII but shouldn't flag normal docs
        # Real docs mix ASCII + unicode — let's confirm majority-ASCII passes
        md = "Normal markdown text with some unicode: café, naïve. " * 10
        # cafe, naive etc are mostly ASCII — should pass at 0.70 threshold
        assert gate_charset_plausible(md).passed is True


# =========================================================================== #
# gate_text_coverage_minimum
# =========================================================================== #

class TestGateTextCoverageMinimum:
    def test_non_pdf_skipped(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.docx"
        src.write_bytes(b"fake")
        r = gate_text_coverage_minimum("anything", src)
        assert r.passed is True
        assert "skipped" in r.reason.lower()

    def test_pass_when_fitz_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.pdf"
        src.write_bytes(b"%PDF")
        with patch.dict("sys.modules", {"fitz": None}):
            r = gate_text_coverage_minimum("anything", src)
        assert r.passed is True

    def test_pass_when_source_unreadable(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.pdf"
        src.write_bytes(b"not a pdf")
        # fitz.open will fail — should not raise
        r = gate_text_coverage_minimum("anything", src)
        assert r.passed is True

    def test_pass_when_coverage_above_minimum(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.pdf"
        src.write_bytes(b"%PDF fake")
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Hello world sample text content document"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc
        md = "Hello world sample text content document extra words"
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            r = gate_text_coverage_minimum(md, src, min_coverage=0.4)
        assert r.passed is True

    def test_fail_when_coverage_below_minimum(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.pdf"
        src.write_bytes(b"%PDF fake")
        mock_page = MagicMock()
        mock_page.get_text.return_value = (
            "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        )
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc
        md = "completely unrelated output with none of the original words"
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            r = gate_text_coverage_minimum(md, src, min_coverage=0.8)
        assert r.passed is False
        assert "%" in r.reason


# =========================================================================== #
# run_hard_gates
# =========================================================================== #

class TestRunHardGates:
    def test_all_pass_for_good_staging(self, tmp_path: Path) -> None:
        md = "# Title\n\n" + "Word " * 30
        d = _staging(tmp_path, md=md)
        gates = run_hard_gates(d)
        assert not disqualified(gates)

    def test_short_circuit_on_missing_index_md(self, tmp_path: Path) -> None:
        d = _staging(tmp_path, md=None)
        gates = run_hard_gates(d)
        assert disqualified(gates)
        # All gates should be returned (short-circuited ones marked failed)
        names = {g.gate_name for g in gates}
        assert "index_md_exists" in names
        assert "not_empty" in names

    def test_returns_all_layer1_gates(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        gates = run_hard_gates(d)
        names = {g.gate_name for g in gates}
        assert {"index_md_exists", "not_empty", "no_broken_image_refs", "charset_plausible"} <= names

    def test_layer2_gate_included_when_source_provided(self, tmp_path: Path) -> None:
        d = _staging(tmp_path, md="# H\n\n" + "word " * 30)
        src = tmp_path / "doc.docx"
        src.write_bytes(b"fake")
        gates = run_hard_gates(d, src)
        names = {g.gate_name for g in gates}
        assert "text_coverage_minimum" in names

    def test_layer2_gate_absent_when_no_source(self, tmp_path: Path) -> None:
        d = _staging(tmp_path)
        gates = run_hard_gates(d)
        names = {g.gate_name for g in gates}
        assert "text_coverage_minimum" not in names

    def test_broken_image_ref_disqualifies(self, tmp_path: Path) -> None:
        md = '<img src="images/ghost.png" alt="x" width="1" height="1">\n\n' + "word " * 30
        d = _staging(tmp_path, md=md)
        gates = run_hard_gates(d)
        assert disqualified(gates)
        assert first_failure(gates).gate_name == "no_broken_image_refs"

    def test_empty_md_disqualifies(self, tmp_path: Path) -> None:
        d = _staging(tmp_path, md="   ")
        gates = run_hard_gates(d)
        assert disqualified(gates)
        assert first_failure(gates).gate_name == "not_empty"


# =========================================================================== #
# Helper functions
# =========================================================================== #

class TestHelpers:
    def test_disqualified_false_when_all_pass(self) -> None:
        gates = [HardGateResult("a", True), HardGateResult("b", True)]
        assert disqualified(gates) is False

    def test_disqualified_true_when_any_fail(self) -> None:
        gates = [HardGateResult("a", True), HardGateResult("b", False, "oops")]
        assert disqualified(gates) is True

    def test_first_failure_returns_none_when_all_pass(self) -> None:
        gates = [HardGateResult("a", True)]
        assert first_failure(gates) is None

    def test_first_failure_returns_first_failed(self) -> None:
        gates = [
            HardGateResult("a", True),
            HardGateResult("b", False, "first fail"),
            HardGateResult("c", False, "second fail"),
        ]
        assert first_failure(gates).gate_name == "b"
