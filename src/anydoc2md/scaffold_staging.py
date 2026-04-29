"""Stage QA and fix extension files into the tournament staging root."""

from __future__ import annotations

import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# 2-file merger templates (project-wide + per-document)
# ---------------------------------------------------------------------------

_MERGED_QA_TEMPLATE = '''\
"""Auto-generated QA extension merger: project-wide + per-document."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path as _P


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_here = _P(__file__).parent
_project = _load("_project_qa", _here / "_project_qa_extension.py")
_doc = _load("_doc_qa", _here / "_doc_qa_extension.py")


def _call(mod, fn):
    f = getattr(mod, fn, None)
    return list(f()) if callable(f) else []


def get_disabled_checks():
    return _call(_project, "get_disabled_checks") + _call(_doc, "get_disabled_checks")

def get_additional_md_only_checks():
    return _call(_project, "get_additional_md_only_checks") + _call(_doc, "get_additional_md_only_checks")

def get_additional_md_with_dir_checks():
    return _call(_project, "get_additional_md_with_dir_checks") + _call(_doc, "get_additional_md_with_dir_checks")

def get_additional_source_checks():
    return _call(_project, "get_additional_source_checks") + _call(_doc, "get_additional_source_checks")
'''

_MERGED_FIX_TEMPLATE = '''\
"""Auto-generated fix extension merger: project-wide + per-document."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path as _P


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_here = _P(__file__).parent
_project = _load("_project_fix", _here / "_project_fix_extension.py")
_doc = _load("_doc_fix", _here / "_doc_fix_extension.py")


def apply_fix_extension(source_path, staging_dir, converter_name):
    for mod in (_project, _doc):
        hook = getattr(mod, "apply_fix_extension", None)
        if callable(hook):
            hook(source_path, staging_dir, converter_name)
'''


# ---------------------------------------------------------------------------
# N-file merger generators (--qa-all / --fix-all)
# ---------------------------------------------------------------------------

def _all_qa_merger(load_lines: str) -> str:
    return f'''\
"""Auto-generated QA extension merger: all project extensions."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path as _P


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_here = _P(__file__).parent
_extensions = [
{load_lines}
]


def _call_all(fn):
    result = []
    for mod in _extensions:
        f = getattr(mod, fn, None)
        if callable(f):
            result.extend(f())
    return result


def get_disabled_checks():
    return _call_all("get_disabled_checks")

def get_additional_md_only_checks():
    return _call_all("get_additional_md_only_checks")

def get_additional_md_with_dir_checks():
    return _call_all("get_additional_md_with_dir_checks")

def get_additional_source_checks():
    return _call_all("get_additional_source_checks")
'''


def _all_fix_merger(load_lines: str) -> str:
    return f'''\
"""Auto-generated fix extension merger: all project extensions."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path as _P


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_here = _P(__file__).parent
_extensions = [
{load_lines}
]


def apply_fix_extension(source_path, staging_dir, converter_name):
    for mod in _extensions:
        hook = getattr(mod, "apply_fix_extension", None)
        if callable(hook):
            hook(source_path, staging_dir, converter_name)
'''


def _stage_all_qa(files: list[Path], staging_dir: Path) -> None:
    load_lines = ""
    for i, f in enumerate(files):
        name = f"_all_qa_{i}.py"
        shutil.copy2(f, staging_dir / name)
        load_lines += f'    _load("_all_qa_{i}", _here / "{name}"),\n'
    (staging_dir / "qa_extension.py").write_text(
        _all_qa_merger(load_lines.rstrip()), encoding="utf-8"
    )


def _stage_all_fix(files: list[Path], staging_dir: Path) -> None:
    load_lines = ""
    for i, f in enumerate(files):
        name = f"_all_fix_{i}.py"
        shutil.copy2(f, staging_dir / name)
        load_lines += f'    _load("_all_fix_{i}", _here / "{name}"),\n'
    (staging_dir / "fix_extension.py").write_text(
        _all_fix_merger(load_lines.rstrip()), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def stage_project_scaffolds(
    anydoc2md_dir: Path,
    source: Path,
    staging_dir: Path,
    qa: Path | None = None,
    fix: Path | None = None,
    qa_all: bool = False,
    fix_all: bool = False,
) -> None:
    """Copy/merge extension files into staging_root before the tournament runs.

    Priority (highest to lowest, per extension type):
      --qa-all / --fix-all  → all files in extensions dir
      --qa / --fix          → specific file, merged with per-doc
      per-document scaffold → matched by source filename
    """
    doc_key = source.name
    doc_qa = anydoc2md_dir / "qa-extensions" / f"{doc_key}.py"
    doc_fix = anydoc2md_dir / "fix-extensions" / f"{doc_key}.py"

    # Collect all-extension file lists when requested
    all_qa_files: list[Path] = []
    all_fix_files: list[Path] = []
    if qa_all:
        all_qa_files = sorted((anydoc2md_dir / "qa-extensions").glob("*.py"))
    if fix_all:
        all_fix_files = sorted((anydoc2md_dir / "fix-extensions").glob("*.py"))

    has_pqa = qa is not None and qa.exists()
    has_dqa = doc_qa.exists()
    has_pfix = fix is not None and fix.exists()
    has_dfix = doc_fix.exists()

    needs_staging = (
        all_qa_files or all_fix_files
        or has_pqa or has_dqa or has_pfix or has_dfix
    )
    if not needs_staging:
        return
    staging_dir.mkdir(parents=True, exist_ok=True)

    # QA extension
    if all_qa_files:
        _stage_all_qa(all_qa_files, staging_dir)
    elif has_pqa and has_dqa:
        shutil.copy2(qa, staging_dir / "_project_qa_extension.py")
        shutil.copy2(doc_qa, staging_dir / "_doc_qa_extension.py")
        (staging_dir / "qa_extension.py").write_text(_MERGED_QA_TEMPLATE, encoding="utf-8")
    elif has_pqa:
        shutil.copy2(qa, staging_dir / "qa_extension.py")
    elif has_dqa:
        shutil.copy2(doc_qa, staging_dir / "qa_extension.py")

    # Fix extension
    if all_fix_files:
        _stage_all_fix(all_fix_files, staging_dir)
    elif has_pfix and has_dfix:
        shutil.copy2(fix, staging_dir / "_project_fix_extension.py")
        shutil.copy2(doc_fix, staging_dir / "_doc_fix_extension.py")
        (staging_dir / "fix_extension.py").write_text(_MERGED_FIX_TEMPLATE, encoding="utf-8")
    elif has_pfix:
        shutil.copy2(fix, staging_dir / "fix_extension.py")
    elif has_dfix:
        shutil.copy2(doc_fix, staging_dir / "fix_extension.py")
