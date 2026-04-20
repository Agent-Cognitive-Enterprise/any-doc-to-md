"""
Hard gates — fast, binary disqualification checks for converter output.

Run these BEFORE the LLM judge to avoid wasting tokens on obviously bad
conversions.  Unlike the soft checks in checks.py, every gate is:
  - binary: pass or disqualify (no "warn")
  - cheap: no subprocesses, minimal I/O
  - early-exit: one failure is enough to disqualify

Usage:
    from anydoc2md.output_qa.hard_gates import run_hard_gates

    gates = run_hard_gates(staging_dir, source_path)
    failed = [g for g in gates if not g.passed]
    if failed:
        print("Disqualified:", failed[0].reason)

Layer 1 gates (output only):   gate_index_md_exists, gate_not_empty,
                                gate_no_broken_image_refs, gate_charset_plausible
Layer 2 gates (source needed):  gate_text_coverage_minimum (PDF only)
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds (module-level so callers can override in tests)
# ---------------------------------------------------------------------------

MIN_MARKDOWN_CHARS: int = 100
MIN_PRINTABLE_RATIO: float = 0.70   # fraction of chars that must be printable (Unicode)
MIN_WORD_COVERAGE: float = 0.40     # minimum sampled-word hit-rate vs source PDF
COVERAGE_SAMPLE_SIZE: int = 12

_PRINTABLE = set(string.printable)
_REPLACEMENT_CHAR = "\ufffd"
_CONTENT_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

from anydoc2md.output_qa.image_refs import extract_image_srcs, resolve_local_image_ref


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HardGateResult:
    gate_name: str
    passed: bool
    reason: str = ""   # empty when passed=True; human-readable when passed=False

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Individual gates
# ---------------------------------------------------------------------------

def gate_index_md_exists(staging_dir: Path) -> HardGateResult:
    """staging_dir/index.md must exist."""
    exists = (staging_dir / "index.md").exists()
    return HardGateResult(
        gate_name="index_md_exists",
        passed=exists,
        reason="" if exists else "No index.md found in staging dir.",
    )


def gate_not_empty(md_text: str, *, min_chars: int = MIN_MARKDOWN_CHARS) -> HardGateResult:
    """Markdown must contain at least min_chars non-whitespace characters."""
    count = len(md_text.strip())
    passed = count >= min_chars
    return HardGateResult(
        gate_name="not_empty",
        passed=passed,
        reason="" if passed else f"Output too short: {count} chars (minimum {min_chars}).",
    )


def gate_no_broken_image_refs(md_text: str, staging_dir: Path) -> HardGateResult:
    """Every local image reference must resolve to an existing file under staging_dir."""
    missing: list[str] = []
    for src in extract_image_srcs(md_text):
        _path, reason = resolve_local_image_ref(staging_dir, src)
        if reason is not None:
            missing.append(reason)
    passed = not missing
    return HardGateResult(
        gate_name="no_broken_image_refs",
        passed=passed,
        reason="" if passed else (
            f"{len(missing)} image ref(s) broken: " + ", ".join(missing[:3])
            + (" …" if len(missing) > 3 else "")
        ),
    )


def gate_charset_plausible(md_text: str, *, min_ratio: float = MIN_PRINTABLE_RATIO) -> HardGateResult:
    """
    Fraction of printable characters must be >= min_ratio.

    A very low ratio indicates encoding corruption or binary junk leaking into
    the markdown (common with some docx → md converters on Windows files).
    Short documents (< 200 chars) are skipped — too few chars to be reliable.
    """
    if len(md_text) < 200:
        return HardGateResult(gate_name="charset_plausible", passed=True,
                              reason="Document too short for reliable charset check — skipped.")

    def _good_char(c: str) -> bool:
        if c in "\n\r\t":
            return True
        if c == _REPLACEMENT_CHAR:
            return False
        return c.isprintable()

    good_count = sum(1 for c in md_text if _good_char(c))
    ratio = good_count / len(md_text)
    passed = ratio >= min_ratio
    return HardGateResult(
        gate_name="charset_plausible",
        passed=passed,
        reason="" if passed else (
            f"Only {ratio*100:.1f}% printable chars "
            f"(minimum {min_ratio*100:.0f}%) — likely encoding corruption."
        ),
    )


def gate_text_coverage_minimum(
    md_text: str,
    source_path: Path,
    *,
    min_coverage: float = MIN_WORD_COVERAGE,
) -> HardGateResult:
    """
    Layer 2 — PDF only.  At least min_coverage fraction of sampled content
    words from the source must appear in the markdown output.

    A coverage below this threshold indicates the converter lost most of the
    text (e.g. image-only output, failed OCR, or empty page extraction).
    """
    if source_path.suffix.lower() != ".pdf":
        return HardGateResult(
            gate_name="text_coverage_minimum",
            passed=True,
            reason="Non-PDF source — text coverage gate skipped.",
        )

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return HardGateResult(
            gate_name="text_coverage_minimum",
            passed=True,
            reason="PyMuPDF not installed — text coverage gate skipped.",
        )

    try:
        doc = fitz.open(str(source_path))
        source_text = "\n".join(page.get_text("text", sort=True) for page in doc)
        doc.close()
    except Exception as exc:
        return HardGateResult(
            gate_name="text_coverage_minimum",
            passed=True,
            reason=f"Could not read source PDF ({exc}) — gate skipped.",
        )

    unique_words = sorted(set(w.casefold() for w in _CONTENT_WORD_RE.findall(source_text)))
    if not unique_words:
        return HardGateResult(
            gate_name="text_coverage_minimum",
            passed=True,
            reason="No content words found in source PDF — gate skipped.",
        )

    step = max(1, len(unique_words) // COVERAGE_SAMPLE_SIZE)
    sample = unique_words[::step][:COVERAGE_SAMPLE_SIZE]

    md_folded = md_text.casefold()
    hits = sum(1 for w in sample if w in md_folded)
    coverage = hits / len(sample)

    passed = coverage >= min_coverage
    return HardGateResult(
        gate_name="text_coverage_minimum",
        passed=passed,
        reason="" if passed else (
            f"Text coverage {coverage*100:.0f}% is below minimum {min_coverage*100:.0f}% "
            f"({hits}/{len(sample)} sampled words found)."
        ),
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_hard_gates(
    staging_dir: Path,
    source_path: Path | None = None,
) -> list[HardGateResult]:
    """
    Run all applicable hard gates against a staging directory.

    Layer 1 gates always run.
    Layer 2 gates run only when source_path is provided.

    Returns a list of HardGateResult.  Order: index_md_exists first (if that
    fails, subsequent gates that need md_text are auto-passed with a note, since
    there is nothing to read).
    """
    results: list[HardGateResult] = []

    # Gate 1: must have index.md before we can do anything else
    g1 = gate_index_md_exists(staging_dir)
    results.append(g1)

    if not g1.passed:
        # Short-circuit: remaining gates need md_text
        skipped_reason = "Skipped — index.md missing."
        for name in ("not_empty", "no_broken_image_refs", "charset_plausible"):
            results.append(HardGateResult(gate_name=name, passed=False, reason=skipped_reason))
        if source_path is not None:
            results.append(HardGateResult(
                gate_name="text_coverage_minimum", passed=False, reason=skipped_reason,
            ))
        return results

    md_text = (staging_dir / "index.md").read_text(encoding="utf-8", errors="replace")

    results.append(gate_not_empty(md_text))
    results.append(gate_no_broken_image_refs(md_text, staging_dir))
    results.append(gate_charset_plausible(md_text))

    if source_path is not None:
        results.append(gate_text_coverage_minimum(md_text, source_path))

    return results


def disqualified(gates: list[HardGateResult]) -> bool:
    """True if any gate failed."""
    return any(not g.passed for g in gates)


def first_failure(gates: list[HardGateResult]) -> HardGateResult | None:
    """Return the first failing gate, or None if all passed."""
    return next((g for g in gates if not g.passed), None)
