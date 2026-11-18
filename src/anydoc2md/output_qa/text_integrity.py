"""Flag visible encoding corruption without deleting or rewriting source text."""
from __future__ import annotations

import re

from .result import CheckResult

CORRUPT_TEXT = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def check_text_integrity(md_text: str) -> CheckResult:
    details = []
    affected = 0
    for number, line in enumerate(md_text.split("\n"), 1):
        codes = sorted({f"U+{ord(match[0]):04X}" for match in CORRUPT_TEXT.finditer(line)})
        if codes:
            affected += 1
            if len(details) < 100:
                details.append(f"Line {number}: {', '.join(codes)}")
    return CheckResult(
        name="text_integrity", layer=1, status="warn" if affected else "pass",
        message=f"{affected} line(s) contain replacement or unexpected control characters; source review required."
        if affected else "No replacement or unexpected control characters.",
        details=details, violation_type="text_corruption" if affected else "",
        severity="high" if affected else "", confidence=1.0 if affected else None,
    )
