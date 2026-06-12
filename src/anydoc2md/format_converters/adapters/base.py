"""
AdapterResult — shared output contract for all converter adapters.

Every adapter must:
  1. Accept (source_path: Path, staging_dir: Path) — staging_dir is
     method-scoped: staging_root/{minio_path}/{method_name}/
  2. Write index.md + images/ into staging_dir on success
  3. Return an AdapterResult regardless of success or failure

Adapters must NOT raise on conversion error — capture it in AdapterResult.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


# ------------------------------------------------------------------ #
# Result dataclass
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class AdapterResult:
    """Output of one converter run against one source document."""

    method_name: str
    method_version: str
    command_invoked: str          # full shell command for reproducibility
    exit_code: int                # 0 = ok; -1 = internal error (not subprocess)
    staging_dir: Path             # method-scoped staging dir
    timing_ms: int
    status: str                   # "ok" | "error" | "timeout" | "unsupported"
    stderr: str = ""              # truncated to 2000 chars
    error_message: str = ""       # human-readable summary when status != "ok"
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def markdown_path(self) -> Path:
        return self.staging_dir / "index.md"

    @property
    def assets_dir(self) -> Path:
        return self.staging_dir / "images"

    @property
    def succeeded(self) -> bool:
        return self.status == "ok" and self.markdown_path.exists()

    @property
    def markdown_text(self) -> str:
        if self.markdown_path.exists():
            return self.markdown_path.read_text(encoding="utf-8", errors="replace")
        return ""

    def to_dict(self) -> dict:
        payload = {
            "method_name": self.method_name,
            "method_version": self.method_version,
            "command_invoked": self.command_invoked,
            "exit_code": self.exit_code,
            "staging_dir": str(self.staging_dir),
            "timing_ms": self.timing_ms,
            "status": self.status,
            "stderr": self.stderr,
            "error_message": self.error_message,
            "markdown_chars": len(self.markdown_text),
        }
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload

    def save_result_json(self) -> None:
        """Write adapter_result.json into staging_dir for later inspection."""
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        path = self.staging_dir / "adapter_result.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


# ------------------------------------------------------------------ #
# Subprocess helper
# ------------------------------------------------------------------ #

def run_subprocess(
    cmd: list[str],
    *,
    timeout_s: int = 300,
    cwd: Path | None = None,
) -> tuple[int, str, str, int]:
    """
    Run a subprocess command and return (exit_code, stdout, stderr, timing_ms).

    On timeout returns (-2, "", "Timed out after {n}s", timing_ms).
    """
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=cwd,
        )
        timing_ms = int((time.monotonic() - t0) * 1000)
        return result.returncode, result.stdout, result.stderr[-2000:], timing_ms
    except subprocess.TimeoutExpired:
        timing_ms = int((time.monotonic() - t0) * 1000)
        return -2, "", f"Timed out after {timeout_s}s", timing_ms
    except Exception as exc:
        timing_ms = int((time.monotonic() - t0) * 1000)
        return -1, "", str(exc), timing_ms


def error_result(
    method_name: str,
    method_version: str,
    command: str,
    staging_dir: Path,
    timing_ms: int,
    message: str,
    exit_code: int = -1,
    status: str = "error",
) -> AdapterResult:
    """Convenience constructor for failed adapter runs."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    result = AdapterResult(
        method_name=method_name,
        method_version=method_version,
        command_invoked=command,
        exit_code=exit_code,
        staging_dir=staging_dir,
        timing_ms=timing_ms,
        status=status,
        error_message=message[:500],
    )
    result.save_result_json()
    return result


def find_cli(name: str) -> str | None:
    """Return full path to CLI tool, or None if not on PATH."""
    return shutil.which(name)
