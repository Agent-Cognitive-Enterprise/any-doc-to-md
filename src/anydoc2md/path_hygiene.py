"""Node-type-robust filesystem removal shared across staging and repair stages.

`remove_path` is a leaf utility with no project dependencies, so modules that sit
at different layers - staging hygiene, paragraph repair, fix application - can
all reuse one removal helper instead of re-implementing the file/symlink/directory
branching. Keeping it dependency-free is deliberate: `staging_hygiene` imports
from `paragraph_repair.application`, so hosting `remove_path` in either of those
modules would force the other into an import cycle.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import TracebackType


def remove_path(path: Path) -> None:
    """Remove whatever is at `path` — file, symlink, or directory; no-op if absent.

    Callers test output slots with `Path.exists()`, which is true for a directory
    or symlink as well as a regular file, so a slot must be cleared regardless of
    node type. A symlink is unlinked without following it (the target is left
    untouched), so a symlink to a directory is never recursed into. A broken
    symlink is still a symlink and is unlinked even though it does not `exists()`.
    A real directory is removed recursively.
    """
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            _rmtree_missing_ok(path)
    except FileNotFoundError:
        # Concurrent hygiene paths may have already removed the slot after the
        # node-type probe. Missing is still a successful cleanup outcome.
        return


def _rmtree_missing_ok(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_ignore_missing_onexc)
    else:
        shutil.rmtree(path, onerror=_ignore_missing_onerror)


def _ignore_missing_onexc(
    function: object,
    path: str,
    exc: BaseException,
) -> None:
    if isinstance(exc, FileNotFoundError):
        return
    raise exc


def _ignore_missing_onerror(
    function: object,
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
) -> None:
    exc = exc_info[1]
    if isinstance(exc, FileNotFoundError):
        return
    raise exc
