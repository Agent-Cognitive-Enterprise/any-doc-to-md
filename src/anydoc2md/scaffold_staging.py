"""Stage QA and in-house extension files into the tournament staging root."""

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

_MERGED_INHOUSE_TEMPLATE = '''\
"""Auto-generated in-house extension merger: project-wide + per-document."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path as _P


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_here = _P(__file__).parent
_project = _load("_project_inhouse", _here / "_project_inhouse_extension.py")
_doc = _load("_doc_inhouse", _here / "_doc_inhouse_extension.py")


def apply_inhouse_extension(source_path, staging_dir, converter_name):
    for mod in (_project, _doc):
        hook = getattr(mod, "apply_inhouse_extension", None)
        if callable(hook):
            hook(source_path, staging_dir, converter_name)
'''


# ---------------------------------------------------------------------------
# N-file merger generators (--project-qa-all / --project-inhouse-all)
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


def _all_inhouse_merger(load_lines: str) -> str:
    return f'''\
"""Auto-generated in-house extension merger: all project extensions."""
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


def apply_inhouse_extension(source_path, staging_dir, converter_name):
    for mod in _extensions:
        hook = getattr(mod, "apply_inhouse_extension", None)
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


def _stage_all_inhouse(files: list[Path], staging_dir: Path) -> None:
    load_lines = ""
    for i, f in enumerate(files):
        name = f"_all_inhouse_{i}.py"
        shutil.copy2(f, staging_dir / name)
        load_lines += f'    _load("_all_inhouse_{i}", _here / "{name}"),\n'
    (staging_dir / "inhouse_extension.py").write_text(
        _all_inhouse_merger(load_lines.rstrip()), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def stage_project_scaffolds(
    anydoc2md_dir: Path,
    source: Path,
    staging_dir: Path,
    project_qa: Path | None = None,
    project_inhouse: Path | None = None,
    project_qa_all: bool = False,
    project_inhouse_all: bool = False,
) -> None:
    """Copy/merge extension files into staging_root before the tournament runs.

    Priority (highest to lowest, per extension type):
      --project-qa-all / --project-inhouse-all  → all files in extensions dir
      --project-qa / --project-inhouse          → specific file, merged with per-doc
      per-document scaffold                     → matched by source filename
    """
    doc_key = source.name
    doc_qa = anydoc2md_dir / "qa-extensions" / f"{doc_key}.py"
    doc_inhouse = anydoc2md_dir / "inhouse-extensions" / f"{doc_key}.py"

    # Collect all-extension file lists when requested
    all_qa_files: list[Path] = []
    all_inhouse_files: list[Path] = []
    if project_qa_all:
        all_qa_files = sorted((anydoc2md_dir / "qa-extensions").glob("*.py"))
    if project_inhouse_all:
        all_inhouse_files = sorted((anydoc2md_dir / "inhouse-extensions").glob("*.py"))

    has_pqa = project_qa is not None and project_qa.exists()
    has_dqa = doc_qa.exists()
    has_pih = project_inhouse is not None and project_inhouse.exists()
    has_dih = doc_inhouse.exists()

    needs_staging = (
        all_qa_files or all_inhouse_files
        or has_pqa or has_dqa or has_pih or has_dih
    )
    if not needs_staging:
        return
    staging_dir.mkdir(parents=True, exist_ok=True)

    # QA extension
    if all_qa_files:
        _stage_all_qa(all_qa_files, staging_dir)
    elif has_pqa and has_dqa:
        shutil.copy2(project_qa, staging_dir / "_project_qa_extension.py")
        shutil.copy2(doc_qa, staging_dir / "_doc_qa_extension.py")
        (staging_dir / "qa_extension.py").write_text(_MERGED_QA_TEMPLATE, encoding="utf-8")
    elif has_pqa:
        shutil.copy2(project_qa, staging_dir / "qa_extension.py")
    elif has_dqa:
        shutil.copy2(doc_qa, staging_dir / "qa_extension.py")

    # In-house extension
    if all_inhouse_files:
        _stage_all_inhouse(all_inhouse_files, staging_dir)
    elif has_pih and has_dih:
        shutil.copy2(project_inhouse, staging_dir / "_project_inhouse_extension.py")
        shutil.copy2(doc_inhouse, staging_dir / "_doc_inhouse_extension.py")
        (staging_dir / "inhouse_extension.py").write_text(_MERGED_INHOUSE_TEMPLATE, encoding="utf-8")
    elif has_pih:
        shutil.copy2(project_inhouse, staging_dir / "inhouse_extension.py")
    elif has_dih:
        shutil.copy2(doc_inhouse, staging_dir / "inhouse_extension.py")
