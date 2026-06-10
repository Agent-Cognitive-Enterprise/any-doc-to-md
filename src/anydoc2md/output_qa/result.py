"""Shared result model for programmatic output QA checks."""
from __future__ import annotations

from dataclasses import dataclass, field


def issue_metadata(
    violation_type: str,
    severity: str,
    confidence: float,
) -> dict[str, object]:
    """Return explicit structured metadata fields for an issue result."""
    return {
        "violation_type": violation_type,
        "severity": severity,
        "confidence": confidence,
    }


@dataclass
class CheckResult:
    """One programmatic QA check result.

    The first five fields are the original public shape used throughout the
    package. The optional violation fields are additive metadata for consumers
    that need structured issue classification; scoring still uses ``status``
    and the configured check weights.
    """

    name: str
    layer: int           # 1 = output-only, 2 = requires source
    status: str          # "pass" | "warn" | "fail"
    message: str
    details: list[str] = field(default_factory=list)
    violation_type: str = ""
    severity: str = ""
    confidence: float | None = None

    def to_dict(self) -> dict:
        payload: dict[str, object] = {
            "name": self.name,
            "layer": self.layer,
            "status": self.status,
            "message": self.message,
            "details": list(self.details),
        }
        if self.violation_type:
            payload["violation_type"] = self.violation_type
        if self.severity:
            payload["severity"] = self.severity
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload
