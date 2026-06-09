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


def _error_adapter_result(staging_dir: Path, name: str) -> AdapterResult:
    return AdapterResult(
        method_name=name,
        method_version="1",
        command_invoked="",
        exit_code=1,
        staging_dir=staging_dir,
        timing_ms=1,
        status="error",
        error_message="failed",
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


def test_run_tournament_clears_stale_outputs_before_failed_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FailingAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            assert not (staging_dir / "index.md").exists()
            assert not (staging_dir / "images").exists()
            assert not (staging_dir / "index_fixed.md").exists()
            return _error_adapter_result(staging_dir, "stub")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: FailingAdapter)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "stub"
    staging_dir.mkdir(parents=True)
    (staging_dir / "index.md").write_text("stale prior output\n", encoding="utf-8")
    (staging_dir / "index_fixed.md").write_text("stale fixed output\n", encoding="utf-8")
    images = staging_dir / "images"
    images.mkdir()
    (images / "old.png").write_bytes(b"old")
    (staging_dir / "notes.txt").write_text("keep", encoding="utf-8")

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["stub"], max_workers=1
    )

    assert results[0].status == "error"
    assert not (staging_dir / "index.md").exists()
    assert not (staging_dir / "index_fixed.md").exists()
    assert not (staging_dir / "images").exists()
    assert (staging_dir / "notes.txt").read_text(encoding="utf-8") == "keep"


def test_run_tournament_removes_partial_outputs_from_failed_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class PartialFailingAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            (staging_dir / "index.md").write_text("partial current output\n", encoding="utf-8")
            (staging_dir / "index_fixed.md").write_text("partial fixed output\n", encoding="utf-8")
            images = staging_dir / "images"
            images.mkdir()
            (images / "partial.png").write_bytes(b"partial")
            return _error_adapter_result(staging_dir, "stub")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: PartialFailingAdapter)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "stub"

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["stub"], max_workers=1
    )

    assert results[0].status == "error"
    assert not (staging_dir / "index.md").exists()
    assert not (staging_dir / "index_fixed.md").exists()
    assert not (staging_dir / "images").exists()


def test_run_tournament_failed_cleanup_uses_assigned_staging_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "index.md").write_text("do not touch\n", encoding="utf-8")

    class WrongPathFailingAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            (staging_dir / "index.md").write_text("partial current output\n", encoding="utf-8")
            result = _error_adapter_result(outside_dir, "stub")
            return result

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: WrongPathFailingAdapter)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "stub"

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["stub"], max_workers=1
    )

    assert results[0].status == "error"
    assert results[0].staging_dir == staging_dir
    assert not (staging_dir / "index.md").exists()
    assert (outside_dir / "index.md").read_text(encoding="utf-8") == "do not touch\n"


def test_run_tournament_clears_stale_outputs_when_adapter_import_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_import(_path: str):
        raise ImportError("missing adapter dependency")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", fail_import)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "stub"
    staging_dir.mkdir(parents=True)
    (staging_dir / "index.md").write_text("stale prior output\n", encoding="utf-8")
    (staging_dir / "index_fixed.md").write_text("stale fixed output\n", encoding="utf-8")
    images = staging_dir / "images"
    images.mkdir()
    (images / "old.png").write_bytes(b"old")

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["stub"], max_workers=1
    )

    assert results[0].status == "error"
    assert "missing adapter dependency" in results[0].error_message
    assert not (staging_dir / "index.md").exists()
    assert not (staging_dir / "index_fixed.md").exists()
    assert not (staging_dir / "images").exists()
    assert (staging_dir / "adapter_result.json").exists()


def test_run_tournament_success_does_not_keep_stale_images(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StubAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            return _ok_result(staging_dir, "stub")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"stub": "stub.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: StubAdapter)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "stub"
    images = staging_dir / "images"
    images.mkdir(parents=True)
    (images / "old.png").write_bytes(b"old")

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["stub"], max_workers=1
    )

    assert results[0].succeeded is True
    assert (staging_dir / "index.md").read_text(encoding="utf-8") == "# ok\n"
    assert not (staging_dir / "images").exists()


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


def test_run_tournament_wall_clock_timeout_produces_error_result(tmp_path: Path, monkeypatch) -> None:
    import threading

    class HungAdapter:
        @staticmethod
        def run(source_path: Path, staging_dir: Path, *, timeout_s: int = 0) -> AdapterResult:
            threading.Event().wait(timeout=0.05)
            return _ok_result(staging_dir, "hung")

    monkeypatch.setattr(runner, "_ADAPTER_MODULES", {"hung": "hung.module"})
    monkeypatch.setattr(runner.importlib, "import_module", lambda _path: HungAdapter)
    monkeypatch.setattr(runner, "_THREAD_GRACE_S", 0)
    source = tmp_path / "doc.txt"
    source.write_text("hello", encoding="utf-8")
    staging_dir = tmp_path / "staging" / "hung"
    staging_dir.mkdir(parents=True)
    (staging_dir / "index.md").write_text("stale prior output\n", encoding="utf-8")
    (staging_dir / "index_fixed.md").write_text("stale fixed output\n", encoding="utf-8")
    images = staging_dir / "images"
    images.mkdir()
    (images / "old.png").write_bytes(b"old")

    results = runner.run_tournament(
        source, tmp_path / "staging", adapters=["hung"], timeout_s=0, max_workers=1
    )

    assert len(results) == 1
    assert results[0].method_name == "hung"
    assert results[0].status == "timeout"
    assert not (staging_dir / "index.md").exists()
    assert not (staging_dir / "index_fixed.md").exists()
    assert not (staging_dir / "images").exists()
