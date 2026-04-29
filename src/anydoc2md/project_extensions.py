"""Project-local extension loading for QA and in-house conversion hooks."""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable

from anydoc2md.output_qa.checks import CheckResult

QA_EXTENSION_FILENAME = "qa_extension.py"
FIX_EXTENSION_FILENAME = "fix_extension.py"

MdOnlyCheck = Callable[[str], CheckResult]
MdWithDirCheck = Callable[[str, Path], CheckResult]
SourceCheck = Callable[[str, Path], CheckResult]


@dataclass(frozen=True)
class QAExtensionSpec:
    disabled_checks: frozenset[str] = frozenset()
    md_only_checks: tuple[MdOnlyCheck, ...] = ()
    md_with_dir_checks: tuple[MdWithDirCheck, ...] = ()
    source_checks: tuple[SourceCheck, ...] = ()
    load_errors: tuple[str, ...] = ()


def load_qa_extension(staging_dir: Path) -> QAExtensionSpec:
    """Load an optional QA extension module from the trusted document root."""
    extension_path = _resolve_trusted_hook_path(staging_dir, QA_EXTENSION_FILENAME)
    if extension_path is None:
        return QAExtensionSpec()

    try:
        module = _load_module(extension_path, "qa_extension")
    except Exception as exc:
        return QAExtensionSpec(load_errors=(f"Failed to load {extension_path.name}: {exc}",))

    try:
        disabled_checks = frozenset(_as_string_list(_call_optional(module, "get_disabled_checks")))
        md_only_checks = tuple(_as_callable_list(_call_optional(module, "get_additional_md_only_checks")))
        md_with_dir_checks = tuple(_as_callable_list(_call_optional(module, "get_additional_md_with_dir_checks")))
        source_checks = tuple(_as_callable_list(_call_optional(module, "get_additional_source_checks")))
    except Exception as exc:
        return QAExtensionSpec(load_errors=(f"Invalid QA extension in {extension_path.name}: {exc}",))

    return QAExtensionSpec(
        disabled_checks=disabled_checks,
        md_only_checks=md_only_checks,
        md_with_dir_checks=md_with_dir_checks,
        source_checks=source_checks,
    )


def apply_fix_extension(
    *,
    source_path: Path,
    staging_dir: Path,
    converter_name: str,
) -> None:
    """Run an optional fix extension hook from the trusted document root."""
    extension_path = _resolve_trusted_hook_path(staging_dir, FIX_EXTENSION_FILENAME)
    if extension_path is None:
        return

    module = _load_module(extension_path, "fix_extension")
    hook = getattr(module, "apply_fix_extension", None)
    if hook is None:
        raise ValueError(f"{extension_path.name} must define apply_fix_extension()")
    if not callable(hook):
        raise TypeError(f"{extension_path.name} apply_fix_extension is not callable")
    hook(source_path, staging_dir, converter_name)


def resolve_override_path(staging_dir: Path, filename: str) -> Path | None:
    """Resolve a staged override file from the adapter dir or document root."""
    return _resolve_staged_file_path(staging_dir, filename)


def _resolve_trusted_hook_path(staging_dir: Path, filename: str) -> Path | None:
    path = staging_dir.parent / filename
    if path.exists():
        return path
    return None


def _resolve_staged_file_path(staging_dir: Path, filename: str) -> Path | None:
    candidates = [staging_dir / filename, staging_dir.parent / filename]
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_module(path: Path, suffix: str) -> ModuleType:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    module_name = f"anydoc2md_{suffix}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call_optional(module: ModuleType, name: str):
    value = getattr(module, name, None)
    if value is None:
        return ()
    if not callable(value):
        raise TypeError(f"{name} must be callable when defined")
    return value()


def _as_string_list(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raise TypeError("Expected an iterable of strings, not a single string")
    return [str(value) for value in values]


def _as_callable_list(values) -> list[Callable]:
    if values is None:
        return []
    result: list[Callable] = []
    for value in values:
        if not callable(value):
            raise TypeError("Expected only callable QA extension hooks")
        result.append(value)
    return result
