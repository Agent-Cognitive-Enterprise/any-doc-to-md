"""Source-aware programmatic QA checks."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from anydoc2md.output_qa.image_refs import extract_image_srcs, image_ref_key
from anydoc2md.output_qa.result import CheckResult, issue_metadata

_CONTENT_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def check_image_count_match(md_text: str, source_path: Path) -> CheckResult:
    """
    Unique image count in source PDF must match image references in Markdown.

    Counts both HTML <img> tags and Markdown ![]() refs so that adapters
    which haven't yet been through annotate_image_dimensions (or whose image
    format Pillow couldn't read) are still counted correctly.
    """
    try:
        import fitz
    except ImportError:
        return CheckResult(name="image_count_match", layer=2, status="warn",
                           message="PyMuPDF not installed — skipping image count check.")

    if source_path.suffix.lower() != ".pdf":
        return CheckResult(name="image_count_match", layer=2, status="pass",
                           message="Image count check only implemented for PDF.")

    doc = fitz.open(str(source_path))
    seen: set[str] = set()
    for page in doc:
        for img_ref in page.get_images(full=True):
            try:
                base = doc.extract_image(img_ref[0])
                digest = hashlib.sha256(base.get("image", b"")).hexdigest()[:16]
                seen.add(digest)
            except Exception:
                pass
    doc.close()

    source_count = len(seen)
    md_refs = {image_ref_key(src) for src in extract_image_srcs(md_text)}
    md_count = len(md_refs)

    if source_count == 0 and md_count == 0:
        return CheckResult(name="image_count_match", layer=2, status="pass",
                           message="No images in source or output.")
    if md_count == source_count:
        return CheckResult(name="image_count_match", layer=2, status="pass",
                           message=f"{source_count} image(s) in source, {md_count} in output — match.")

    status = "fail" if abs(md_count - source_count) > 1 else "warn"
    return CheckResult(
        name="image_count_match", layer=2, status=status,
        message=f"Source has {source_count} unique image(s), output has {md_count}.",
        details=[f"Difference: {md_count - source_count:+d}"],
        **issue_metadata(
            _image_count_violation_type(md_count, source_count),
            "major" if status == "fail" else "minor",
            0.90,
        ),
    )


def _image_count_violation_type(md_count: int, source_count: int) -> str:
    return "missing_content" if md_count < source_count else "duplicated_content"


def check_text_coverage(
    md_text: str,
    source_path: Path,
    sample_size: int = 12,
) -> CheckResult:
    """
    Sample content words from the source and verify they appear in the output.
    Uses PyMuPDF with sort=True for layout-aware extraction (handles multi-column PDFs).
    Word-level (not phrase-level) coverage — robust to column boundary splitting.
    """
    if source_path.suffix.lower() != ".pdf":
        return CheckResult(name="text_coverage", layer=2, status="pass",
                           message="Text coverage check only implemented for PDF.")
    try:
        import fitz
    except ImportError:
        return CheckResult(name="text_coverage", layer=2, status="warn",
                           message="PyMuPDF not installed — skipping text coverage check.")

    doc = fitz.open(str(source_path))
    source_text = "\n".join(page.get_text("text", sort=True) for page in doc)
    doc.close()

    unique_words = sorted(set(w.casefold() for w in _CONTENT_WORD_RE.findall(source_text)))
    if not unique_words:
        return CheckResult(name="text_coverage", layer=2, status="pass",
                           message="No content words found in source — skipping.")

    step = max(1, len(unique_words) // sample_size)
    sample = unique_words[::step][:sample_size]

    md_folded = md_text.casefold()
    missing = [w for w in sample if w not in md_folded]
    n = len(sample)
    coverage = (n - len(missing)) / n if n else 1.0

    if coverage >= 0.9:
        return CheckResult(
            name="text_coverage", layer=2, status="pass",
            message=f"Word coverage {coverage*100:.0f}% ({n - len(missing)}/{n} sampled words found).",
        )
    status = "fail" if coverage < 0.75 else "warn"
    return CheckResult(
        name="text_coverage", layer=2, status=status,
        message=f"Word coverage {coverage*100:.0f}% — {len(missing)} of {n} sampled words missing.",
        details=missing[:5],
        **issue_metadata(
            "missing_content",
            "major" if status == "fail" else "minor",
            0.80,
        ),
    )
