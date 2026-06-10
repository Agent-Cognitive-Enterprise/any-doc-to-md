from __future__ import annotations

from pathlib import Path

import anydoc2md.path_hygiene as path_hygiene
from anydoc2md.path_hygiene import remove_path


def test_remove_path_missing_is_noop(tmp_path: Path) -> None:
    remove_path(tmp_path / "absent")  # must not raise


def test_remove_path_removes_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")

    remove_path(target)

    assert not target.exists()


def test_remove_path_removes_directory_recursively(tmp_path: Path) -> None:
    target = tmp_path / "dir"
    (target / "nested").mkdir(parents=True)
    (target / "nested" / "leaf.txt").write_text("x", encoding="utf-8")

    remove_path(target)

    assert not target.exists()


def test_remove_path_treats_concurrent_directory_removal_as_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "dir"
    target.mkdir()

    def remove_elsewhere_then_raise(path: Path, **kwargs) -> None:
        path.rmdir()
        raise FileNotFoundError(path)

    monkeypatch.setattr(path_hygiene.shutil, "rmtree", remove_elsewhere_then_raise)

    remove_path(target)

    assert not target.exists()


def test_remove_path_unlinks_symlink_to_file_without_touching_target(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    remove_path(link)

    assert not link.exists()
    assert real.exists()


def test_remove_path_unlinks_symlink_to_directory_without_recursing(
    tmp_path: Path,
) -> None:
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "leaf.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "link_dir"
    link.symlink_to(real_dir, target_is_directory=True)

    remove_path(link)

    assert not link.exists()
    assert real_dir.is_dir()
    assert (real_dir / "leaf.txt").exists()


def test_remove_path_removes_broken_symlink(tmp_path: Path) -> None:
    link = tmp_path / "broken"
    link.symlink_to(tmp_path / "does_not_exist")
    assert link.is_symlink()
    assert not link.exists()  # broken: target absent

    remove_path(link)

    assert not link.is_symlink()
