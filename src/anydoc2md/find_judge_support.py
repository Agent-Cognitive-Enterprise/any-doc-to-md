"""Support helpers for the find_judge CLI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import tempfile
from pathlib import Path

from anydoc2md.judge_probe_case import ProbeCase, build_probe_case


def _env_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _select_models(all_model_ids: list[str], requested_model_names: list[str]) -> list[str]:
    if not requested_model_names:
        return all_model_ids

    requested = [name.strip() for name in requested_model_names if name.strip()]
    requested_set = set(requested)
    available_set = set(all_model_ids)
    missing = [name for name in requested if name not in available_set]
    if missing:
        missing_joined = ", ".join(missing)
        raise ValueError(f"Requested model(s) not found on endpoint: {missing_joined}")

    return [model_id for model_id in all_model_ids if model_id in requested_set]


@contextmanager
def _probe_case_context(
    *,
    keep_artifacts: bool,
    artifacts_dir: Path | None,
) -> Iterator[tuple[ProbeCase, Path | None]]:
    if keep_artifacts:
        if artifacts_dir is not None:
            root = artifacts_dir.expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            probe_case_dir = Path(tempfile.mkdtemp(prefix="anydoc2md-find-judge-", dir=root))
        else:
            probe_case_dir = Path(tempfile.mkdtemp(prefix="anydoc2md-find-judge-"))
        yield build_probe_case(probe_case_dir), probe_case_dir
        return

    with tempfile.TemporaryDirectory(prefix="anydoc2md-find-judge-") as tmp:
        yield build_probe_case(Path(tmp)), None


def _print_artifact_paths(probe_case: ProbeCase, probe_case_dir: Path | None) -> None:
    if probe_case_dir is None:
        return
    print(f"Artifacts kept at: {probe_case_dir}", flush=True)
    print(f"  source:    {probe_case.source_pdf}", flush=True)
    print(f"  candidate: {probe_case.candidate_pdf}", flush=True)
    print(f"  staging:   {probe_case.candidate.staging_dir}", flush=True)
    print("", flush=True)
