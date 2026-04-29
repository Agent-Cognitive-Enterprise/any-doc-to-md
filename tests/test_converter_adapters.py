"""
Functional tests for format_converters/adapters/*.

All tests use .txt source files so they run without PDF/DOCX toolchains
and complete in milliseconds.  External-converter adapters (markitdown,
docling) are tested for their error paths (CLI missing) so they also run
in CI without those tools installed.

Coverage:
  - AdapterResult contract (succeeded, markdown_path, to_dict, save_result_json)
  - run_subprocess: success, timeout, exception
  - error_result constructor
  - inhouse adapter: .txt success, unsupported extension, exception path
  - markitdown adapter: CLI-missing path
  - docling adapter: CLI-missing path, _normalise_assets image rewriting
  - tournament runner: parallel execution, unknown adapter error
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from anydoc2md.format_converters.adapters.base import (
    AdapterResult,
    error_result,
    find_cli,
    run_subprocess,
)
from anydoc2md.format_converters.adapters import docling, inhouse, markitdown, marker, pandoc
from anydoc2md.format_converters.tournament.runner import (
    DEFAULT_ADAPTERS,
    _ADAPTER_MODULES,
    _load_adapter,
    available_adapter_names,
    default_adapter_names,
    run_tournament,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _txt_source(tmp_path: Path, content: str = "Para one.\n\nPara two.") -> Path:
    p = tmp_path / "doc.txt"
    p.write_text(content, encoding="utf-8")
    return p


# =========================================================================== #
# AdapterResult
# =========================================================================== #

class TestAdapterResult:
    def test_succeeded_true_when_ok_and_md_exists(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "index.md").write_text("# Hello")
        r = AdapterResult(
            method_name="test", method_version="1", command_invoked="",
            exit_code=0, staging_dir=staging, timing_ms=10, status="ok",
        )
        assert r.succeeded is True

    def test_succeeded_false_when_no_md(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        r = AdapterResult(
            method_name="test", method_version="1", command_invoked="",
            exit_code=0, staging_dir=staging, timing_ms=10, status="ok",
        )
        assert r.succeeded is False

    def test_succeeded_false_when_error_status(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "index.md").write_text("# Hello")
        r = AdapterResult(
            method_name="test", method_version="1", command_invoked="",
            exit_code=1, staging_dir=staging, timing_ms=10, status="error",
        )
        assert r.succeeded is False

    def test_markdown_text_reads_file(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "index.md").write_text("# Content", encoding="utf-8")
        r = AdapterResult(
            method_name="x", method_version="1", command_invoked="",
            exit_code=0, staging_dir=staging, timing_ms=1, status="ok",
        )
        assert r.markdown_text == "# Content"

    def test_markdown_text_empty_when_missing(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        r = AdapterResult(
            method_name="x", method_version="1", command_invoked="",
            exit_code=0, staging_dir=staging, timing_ms=1, status="error",
        )
        assert r.markdown_text == ""

    def test_to_dict_keys(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        r = AdapterResult(
            method_name="x", method_version="1", command_invoked="cmd",
            exit_code=0, staging_dir=staging, timing_ms=5, status="ok",
        )
        d = r.to_dict()
        for key in ("method_name", "method_version", "command_invoked",
                    "exit_code", "timing_ms", "status", "markdown_chars"):
            assert key in d

    def test_save_result_json_writes_file(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        r = AdapterResult(
            method_name="x", method_version="1", command_invoked="",
            exit_code=0, staging_dir=staging, timing_ms=1, status="ok",
        )
        r.save_result_json()
        data = json.loads((staging / "adapter_result.json").read_text())
        assert data["method_name"] == "x"


# =========================================================================== #
# run_subprocess
# =========================================================================== #

class TestRunSubprocess:
    def test_success(self) -> None:
        code, stdout, stderr, ms = run_subprocess(["echo", "hello"])
        assert code == 0
        assert "hello" in stdout
        assert ms >= 0

    def test_nonzero_exit(self) -> None:
        code, _, _, _ = run_subprocess(["false"])
        assert code != 0

    def test_timeout(self) -> None:
        code, _, stderr, _ = run_subprocess(["sleep", "10"], timeout_s=1)
        assert code == -2
        assert "Timed out" in stderr

    def test_missing_command(self) -> None:
        code, _, stderr, _ = run_subprocess(["this_does_not_exist_xyz"])
        assert code == -1
        assert len(stderr) > 0


# =========================================================================== #
# error_result
# =========================================================================== #

class TestErrorResult:
    def test_status_set(self, tmp_path: Path) -> None:
        r = error_result("x", "1", "cmd", tmp_path / "s", 100, "boom")
        assert r.status == "error"
        assert r.error_message == "boom"
        assert r.succeeded is False

    def test_custom_status(self, tmp_path: Path) -> None:
        r = error_result("x", "1", "cmd", tmp_path / "s", 0, "msg", status="timeout")
        assert r.status == "timeout"


# =========================================================================== #
# inhouse adapter
# =========================================================================== #

class TestInhouseAdapter:
    def test_txt_success(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        staging = tmp_path / "staging"
        r = inhouse.run(src, staging)
        assert r.succeeded
        assert r.status == "ok"
        assert r.method_name == "inhouse"
        assert "Para one" in r.markdown_text

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "file.xyz"
        src.write_text("data")
        r = inhouse.run(src, tmp_path / "staging")
        assert r.status == "unsupported"
        assert not r.succeeded

    def test_missing_source_file_gives_error(self, tmp_path: Path) -> None:
        src = tmp_path / "missing.txt"  # does not exist
        r = inhouse.run(src, tmp_path / "staging")
        assert r.status == "error"
        assert not r.succeeded

    def test_saves_result_json(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        staging = tmp_path / "staging"
        r = inhouse.run(src, staging)
        assert (staging / "adapter_result.json").exists()

    def test_timing_recorded(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        r = inhouse.run(src, tmp_path / "staging")
        assert r.timing_ms >= 0

    def test_supports_returns_true_for_txt(self) -> None:
        assert inhouse.supports(Path("doc.txt")) is True

    def test_supports_returns_false_for_unknown(self) -> None:
        assert inhouse.supports(Path("doc.xyz")) is False

    def test_inhouse_adapter_does_not_apply_fix_extension(self, tmp_path: Path) -> None:
        # Fix extensions are applied by fix_application.apply_fix_extensions
        # after all adapters run, not inside the adapter itself.
        src = _txt_source(tmp_path)
        doc_root = tmp_path / "doc"
        staging = doc_root / "inhouse"
        doc_root.mkdir()
        (doc_root / "fix_extension.py").write_text(
            "def apply_fix_extension(source_path, staging_dir, converter_name):\n"
            "    index_md = staging_dir / 'index.md'\n"
            "    index_md.write_text(\n"
            "        index_md.read_text(encoding='utf-8') + '\\n\\nExtension footer.\\n',\n"
            "        encoding='utf-8',\n"
            "    )\n",
            encoding="utf-8",
        )

        r = inhouse.run(src, staging)

        assert r.succeeded
        assert "Extension footer." not in r.markdown_text


# =========================================================================== #
# markitdown adapter (CLI-missing path)
# =========================================================================== #

class TestMarkitdownAdapter:
    def test_cli_missing_returns_error(self, tmp_path: Path) -> None:
        with patch("anydoc2md.format_converters.adapters.markitdown.find_cli", return_value=None):
            r = markitdown.run(_txt_source(tmp_path), tmp_path / "staging")
        assert r.status == "error"
        assert "not found" in r.error_message.lower()

    def test_unsupported_extension_with_cli_present(self, tmp_path: Path) -> None:
        src = tmp_path / "file.xyz"
        src.write_text("data")
        with patch("anydoc2md.format_converters.adapters.markitdown.find_cli", return_value="/usr/bin/markitdown"):
            with patch("anydoc2md.format_converters.adapters.markitdown._get_version", return_value="0.1"):
                r = markitdown.run(src, tmp_path / "staging")
        assert r.status == "unsupported"

    def test_supports_pdf(self) -> None:
        assert markitdown.supports(Path("doc.pdf")) is True

    def test_supports_txt(self) -> None:
        assert markitdown.supports(Path("doc.txt")) is True


# =========================================================================== #
# docling adapter (CLI-missing + asset normalisation)
# =========================================================================== #

class TestDoclingAdapter:
    def test_cli_missing_returns_error(self, tmp_path: Path) -> None:
        with patch("anydoc2md.format_converters.adapters.docling.find_cli", return_value=None):
            r = docling.run(_txt_source(tmp_path), tmp_path / "staging")
        assert r.status == "error"
        assert "not found" in r.error_message.lower()

    def test_normalise_assets_moves_images_and_rewrites_md(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()

        # Simulate docling output: artifacts dir + MD referencing them
        artifacts = staging / "doc_artifacts"
        artifacts.mkdir()
        (artifacts / "fig1.png").write_bytes(b"PNG1")
        (artifacts / "fig2.png").write_bytes(b"PNG2")

        md_content = (
            "# Title\n\n"
            "![Image](doc_artifacts/fig1.png)\n\n"
            "Text.\n\n"
            "![Image](doc_artifacts/fig2.png)\n"
        )
        (staging / "index.md").write_text(md_content, encoding="utf-8")

        docling._normalise_assets(staging, "doc")

        # Images moved to images/
        assert (staging / "images" / "fig1.png").exists()
        assert (staging / "images" / "fig2.png").exists()
        assert not artifacts.exists()

        # MD references rewritten
        updated = (staging / "index.md").read_text()
        assert "doc_artifacts/" not in updated
        assert "images/fig1.png" in updated
        assert "images/fig2.png" in updated

    def test_normalise_assets_no_op_when_no_artifacts(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "index.md").write_text("# No images")
        (staging / "images").mkdir()
        docling._normalise_assets(staging, "doc")
        assert (staging / "index.md").read_text() == "# No images"

    def test_supports_pdf(self) -> None:
        assert docling.supports(Path("doc.pdf")) is True


# =========================================================================== #
# pandoc adapter
# =========================================================================== #

class TestPandocAdapter:
    def test_cli_missing_returns_error(self, tmp_path: Path) -> None:
        with patch("anydoc2md.format_converters.adapters.pandoc.find_cli", return_value=None):
            r = pandoc.run(_txt_source(tmp_path), tmp_path / "staging")
        assert r.status == "error"
        assert "not found" in r.error_message.lower()

    def test_supports_html(self) -> None:
        assert pandoc.supports(Path("doc.html")) is True

    def test_supports_pdf_is_false(self) -> None:
        assert pandoc.supports(Path("doc.pdf")) is False


# =========================================================================== #
# marker adapter
# =========================================================================== #

class TestMarkerAdapter:
    def test_cli_missing_returns_error(self, tmp_path: Path) -> None:
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch("anydoc2md.format_converters.adapters.marker.find_cli", return_value=None):
            r = marker.run(pdf, tmp_path / "staging")
        assert r.status == "error"
        assert "not found" in r.error_message.lower()

    def test_normalise_output_moves_images_and_rewrites_paths(self, tmp_path: Path) -> None:
        staging = tmp_path / "staging"
        nested = staging / "doc"
        nested.mkdir(parents=True)
        (nested / "page1.md").write_text(
            "# Title\n\n![Figure](doc/images/fig1.png)\n",
            encoding="utf-8",
        )
        (nested / "images").mkdir()
        (nested / "images" / "fig1.png").write_bytes(b"PNG")

        marker._normalise_output(staging)

        assert (staging / "index.md").exists()
        assert (staging / "images" / "fig1.png").exists()
        content = (staging / "index.md").read_text(encoding="utf-8")
        assert "images/fig1.png" in content

    def test_supports_pdf(self) -> None:
        assert marker.supports(Path("doc.pdf")) is True


# =========================================================================== #
# Tournament runner registry
# =========================================================================== #

class TestTournamentRunnerRegistry:
    def test_every_registered_adapter_module_is_importable(self) -> None:
        for name in _ADAPTER_MODULES:
            module = _load_adapter(name)
            assert hasattr(module, "run"), name

    def test_available_adapter_names_matches_registry_order(self) -> None:
        assert available_adapter_names() == list(_ADAPTER_MODULES)

    def test_default_adapter_names_is_inhouse_only(self) -> None:
        assert DEFAULT_ADAPTERS == ["inhouse"]
        assert default_adapter_names() == ["inhouse"]


# =========================================================================== #
# Tournament runner
# =========================================================================== #

class TestTournamentRunner:
    def test_default_selection_runs_default_adapters_only(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        calls: list[str] = []

        class _FakeAdapter:
            def __init__(self, name: str) -> None:
                self._name = name

            def run(self, source_path: Path, staging_dir: Path) -> AdapterResult:
                calls.append(self._name)
                staging_dir.mkdir(parents=True, exist_ok=True)
                (staging_dir / "index.md").write_text(f"# {self._name}", encoding="utf-8")
                return AdapterResult(
                    method_name=self._name,
                    method_version="1",
                    command_invoked="",
                    exit_code=0,
                    staging_dir=staging_dir,
                    timing_ms=1,
                    status="ok",
                )

        with patch(
            "anydoc2md.format_converters.tournament.runner._load_adapter",
            side_effect=lambda name: _FakeAdapter(name),
        ):
            results = run_tournament(src, tmp_path / "staging", adapters=None)

        assert calls == default_adapter_names()
        assert {r.method_name for r in results} == set(default_adapter_names())

    def test_explicit_adapter_list_runs_exactly_requested_adapters(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        results = run_tournament(src, tmp_path / "staging", adapters=["inhouse"])
        assert len(results) == 1
        assert results[0].method_name == "inhouse"

    def test_unknown_adapter_returns_error_result(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        results = run_tournament(src, tmp_path / "staging", adapters=["inhouse", "nonexistent_xyz"])
        names = {r.method_name for r in results}
        assert "inhouse" in names
        nonexistent = next(r for r in results if r.method_name == "nonexistent_xyz")
        assert nonexistent.status == "error"

    def test_all_succeed_for_txt(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        results = run_tournament(src, tmp_path / "staging", adapters=["inhouse"])
        assert all(r.succeeded for r in results)

    def test_staging_subdirs_created_per_adapter(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        staging_root = tmp_path / "staging"
        run_tournament(src, staging_root, adapters=["inhouse"])
        assert (staging_root / "inhouse").is_dir()

    def test_returns_list_even_on_partial_failure(self, tmp_path: Path) -> None:
        src = _txt_source(tmp_path)
        with patch("anydoc2md.format_converters.adapters.markitdown.find_cli", return_value=None):
            results = run_tournament(src, tmp_path / "staging", adapters=["inhouse", "markitdown"])
        assert len(results) == 2
        methods = {r.method_name for r in results}
        assert "inhouse" in methods
        assert "markitdown" in methods
