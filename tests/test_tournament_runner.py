from __future__ import annotations

from pathlib import Path

from anydoc2md.format_converters.adapters.base import AdapterResult
from anydoc2md.format_converters.tournament import runner


def _ok_result(staging_dir: Path, name: str) -> AdapterResult:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "index.md").write_text("# ok\n", encoding="utf-8")
    return AdapterResult(
        method_name=name,
        method_version="1",
        command_invoked="",
        exit_code=0,
        staging_dir=staging_dir,
        timing_ms=1,
        status="ok",
    )


def test_run_tournament_passes_timeout_s(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, int] = {}

    class StubAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            called["timeout_s"] = timeout_s
            return _ok_result(staging_dir, "stub")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: StubAdapter)

    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_root = tmp_path / "staging"
    results = runner.run_tournament(source, staging_root, adapters=["stub"], timeout_s=123, max_workers=1)

    assert called["timeout_s"] == 123
    assert len(results) == 1
    assert results[0].method_name == "stub"


def test_run_tournament_falls_back_when_adapter_has_no_timeout_kwarg(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, bool] = {"called": False}

    class LegacyAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path) -> AdapterResult:
            called["called"] = True
            return _ok_result(staging_dir, "legacy")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"legacy": "legacy.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: LegacyAdapter)

    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_root = tmp_path / "staging"
    results = runner.run_tournament(source, staging_root, adapters=["legacy"], timeout_s=123, max_workers=1)

    assert called["called"] is True
    assert len(results) == 1
    assert results[0].method_name == "legacy"


def test_run_tournament_preserves_explicit_empty_adapter_list(tmp_path: Path, monkeypatch) -> None:
    called = False

    def fail_import(_path: str):
        nonlocal called
        called = True
        raise AssertionError("no adapters should be imported")

    monkeypatch.setattr(runner.importlib, "import_module", fail_import)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")

    results = runner.run_tournament(source, tmp_path / "staging", adapters=[], max_workers=0)

    assert results == []
    assert called is False


def test_run_tournament_clamps_non_positive_max_workers(tmp_path: Path, monkeypatch) -> None:
    class StubAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            return _ok_result(staging_dir, "stub")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: StubAdapter)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")

    results = runner.run_tournament(source, tmp_path / "staging", adapters=["stub"], max_workers=0)

    assert len(results) == 1
    assert results[0].method_name == "stub"
