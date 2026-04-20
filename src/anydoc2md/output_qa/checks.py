"""
QA checks for converted Markdown documents.

Two layers:
  Layer 1 — structural checks on index.md alone (fast, no source needed).
  Layer 2 — fidelity checks comparing index.md against the original source file.

Each check returns a CheckResult.  New checks are added here whenever the
LLM judge finds an issue class that the coding agent codifies programmatically.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    layer: int           # 1 = output-only, 2 = requires source
    status: str          # "pass" | "warn" | "fail"
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Shared regex
# ---------------------------------------------------------------------------

IMG_TAG_RE = re.compile(r'<img\s[^>]*>', re.IGNORECASE)
IMG_SRC_RE = re.compile(r'src="([^"]+)"', re.IGNORECASE)
IMG_WIDTH_RE = re.compile(r'width:\s*([\d.]+)em', re.IGNORECASE)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)', re.MULTILINE)
DOUBLE_BULLET_RE = re.compile(r'^[-*]\s+[•\-\*]\s+', re.MULTILINE)
# Figure/Fig. captions only — Table captions may legitimately be text tables
CAPTION_RE = re.compile(r'^\*(Figure|Fig\.)\s+\d+(\.\d+)*\.\s', re.MULTILINE | re.IGNORECASE)
BOX_HEADING_RE = re.compile(r'^#{1,6}\s+Box\s+\d+(\.\d+)*\.', re.MULTILINE | re.IGNORECASE)


def _lines(md_text: str) -> list[str]:
    return md_text.splitlines()


# ---------------------------------------------------------------------------
# Layer 1 checks
# ---------------------------------------------------------------------------

def check_no_double_bullets(md_text: str) -> CheckResult:
    """No list items that begin with two bullet markers (e.g. '- • text')."""
    matches = DOUBLE_BULLET_RE.findall(md_text)
    if matches:
        return CheckResult(
            name="no_double_bullets", layer=1, status="fail",
            message=f"{len(matches)} list item(s) have double bullet markers.",
            details=[repr(m) for m in matches[:5]],
        )
    return CheckResult(name="no_double_bullets", layer=1, status="pass",
                       message="No double bullet markers found.")


def check_numbered_list_sequential(md_text: str) -> CheckResult:
    """Numbered lists must be sequential (1, 2, 3…) with no gaps or duplicates."""
    issues: list[str] = []
    lines = _lines(md_text)
    i = 0
    while i < len(lines):
        m = re.match(r'^(\d+)\.\s+\S', lines[i])
        if not m:
            i += 1
            continue
        run = [int(m.group(1))]
        j = i + 1
        while j < len(lines):
            m2 = re.match(r'^(\d+)\.\s+\S', lines[j])
            if m2:
                run.append(int(m2.group(1)))
                j += 1
            elif lines[j].strip() == "":
                j += 1
            else:
                break
        if len(run) >= 2:
            for k in range(1, len(run)):
                if run[k] != run[k - 1] + 1:
                    issues.append(f"Gap/duplicate: {run[k-1]} → {run[k]} (near line {i+1})")
        i = j

    if issues:
        return CheckResult(
            name="numbered_list_sequential", layer=1, status="fail",
            message=f"{len(issues)} numbered list sequence issue(s).",
            details=issues[:5],
        )
    return CheckResult(name="numbered_list_sequential", layer=1, status="pass",
                       message="All numbered lists are sequential.")


def check_heading_not_fragmented(md_text: str) -> CheckResult:
    """
    No heading immediately followed by a short lowercase continuation line —
    indicates a multi-line heading that was only partially promoted.
    """
    lines = _lines(md_text)
    issues: list[str] = []
    for i, line in enumerate(lines[:-1]):
        if not HEADING_RE.match(line):
            continue
        next_line = lines[i + 1].strip()
        if not next_line or next_line[0] in "#-*<":
            continue
        heading_text = HEADING_RE.match(line).group(2)
        if not heading_text.endswith((".", "?", "!", ":")):
            if len(next_line) < 60 and next_line[0].islower():
                issues.append(f"Line {i+1}: {line!r} → {next_line!r}")
    if issues:
        return CheckResult(
            name="heading_not_fragmented", layer=1, status="warn",
            message=f"{len(issues)} possible fragmented heading(s).",
            details=issues[:5],
        )
    return CheckResult(name="heading_not_fragmented", layer=1, status="pass",
                       message="No fragmented headings detected.")


def check_caption_near_image(md_text: str) -> CheckResult:
    """
    Every '*Figure X.X. …*' caption must appear within 6 lines of an <img> tag.
    Window is ±6 (not ±3) because multiple captions may stack after one image.
    """
    lines = _lines(md_text)
    img_lines = {i for i, l in enumerate(lines) if IMG_TAG_RE.search(l)}
    issues: list[str] = []

    for i, line in enumerate(lines):
        if not CAPTION_RE.match(line):
            continue
        window = range(max(0, i - 6), min(len(lines), i + 7))
        if not any(j in img_lines for j in window):
            issues.append(f"Line {i+1}: {line.strip()[:80]}")

    if issues:
        return CheckResult(
            name="caption_near_image", layer=1, status="fail",
            message=f"{len(issues)} caption(s) not adjacent to an image.",
            details=issues,
        )
    return CheckResult(name="caption_near_image", layer=1, status="pass",
                       message="All captions are adjacent to an image.")


def check_box_title_precedes_content(md_text: str) -> CheckResult:
    """A 'Box X.X.' heading must be followed by content within 5 lines."""
    lines = _lines(md_text)
    issues: list[str] = []
    for i, line in enumerate(lines):
        if not BOX_HEADING_RE.match(line):
            continue
        content_found = any(
            lines[j].strip() and not lines[j].strip().startswith("#")
            for j in range(i + 1, min(len(lines), i + 6))
        )
        if not content_found:
            issues.append(f"Line {i+1}: {line.strip()}")
    if issues:
        return CheckResult(
            name="box_title_precedes_content", layer=1, status="fail",
            message=f"{len(issues)} Box heading(s) not followed by content.",
            details=issues,
        )
    return CheckResult(name="box_title_precedes_content", layer=1, status="pass",
                       message="All Box headings are followed by content.")


def check_image_size_plausible(md_text: str) -> CheckResult:
    """All <img> widths must be between 1em and 38em."""
    issues: list[str] = []
    for m in IMG_TAG_RE.finditer(md_text):
        tag = m.group(0)
        wm = IMG_WIDTH_RE.search(tag)
        if not wm:
            issues.append(f"Missing width: {tag[:80]}")
            continue
        w = float(wm.group(1))
        if w <= 0:
            issues.append(f"Zero width: {tag[:80]}")
        elif w > 38:
            issues.append(f"Suspiciously large ({w}em): {tag[:80]}")
    if issues:
        return CheckResult(
            name="image_size_plausible", layer=1, status="warn",
            message=f"{len(issues)} image(s) with suspicious size.",
            details=issues,
        )
    return CheckResult(name="image_size_plausible", layer=1, status="pass",
                       message="All image sizes are plausible.")


def check_no_repeated_headings(md_text: str) -> CheckResult:
    """Headings with identical text appearing 3+ times are likely running page headers."""
    headings = [m.group(2).strip() for m in HEADING_RE.finditer(md_text)]
    repeats = {h: n for h, n in Counter(headings).items() if n >= 3}
    if repeats:
        details = [f"{n}× {h!r}" for h, n in sorted(repeats.items(), key=lambda x: -x[1])]
        return CheckResult(
            name="no_repeated_headings", layer=1, status="warn",
            message=f"{len(repeats)} heading(s) repeated 3+ times (possible page headers).",
            details=details,
        )
    return CheckResult(name="no_repeated_headings", layer=1, status="pass",
                       message="No suspiciously repeated headings.")


def check_images_locally_resolvable(md_text: str, staging_dir: Path) -> CheckResult:
    """
    Every <img src="images/..."> in the MD must resolve to an existing file
    in staging_dir.  Catches write failures and path mismatches.
    """
    missing: list[str] = []
    for m in IMG_TAG_RE.finditer(md_text):
        src_m = IMG_SRC_RE.search(m.group(0))
        if not src_m:
            continue
        src = src_m.group(1)
        if not (staging_dir / src).exists():
            missing.append(src)
    if missing:
        return CheckResult(
            name="images_locally_resolvable", layer=1, status="fail",
            message=f"{len(missing)} image(s) referenced in MD but missing on disk.",
            details=missing[:5],
        )
    return CheckResult(name="images_locally_resolvable", layer=1, status="pass",
                       message="All referenced images exist on disk.")


# ---------------------------------------------------------------------------
# Layer 2 checks (require original source file)
# ---------------------------------------------------------------------------

_MD_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


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

    import hashlib
    doc = fitz.open(str(source_path))
    seen: set[str] = set()
    for page in doc:
        for img_ref in page.get_images(full=True):
            try:
                base = doc.extract_image(img_ref[0])
                h = hashlib.sha256(base.get("image", b"")).hexdigest()[:16]
                seen.add(h)
            except Exception:
                pass
    doc.close()

    source_count = len(seen)
    # Count both HTML <img> tags and Markdown ![]() refs (union, not double-count)
    md_count = len(IMG_TAG_RE.findall(md_text)) + len(_MD_IMG_REF_RE.findall(md_text))

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
    )


def check_text_coverage(md_text: str, source_path: Path, sample_size: int = 12) -> CheckResult:
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

    unique_words = sorted(set(
        w.lower() for w in re.findall(r'\b[A-Za-z]{5,}\b', source_text)
    ))
    if not unique_words:
        return CheckResult(name="text_coverage", layer=2, status="pass",
                           message="No content words found in source — skipping.")

    step = max(1, len(unique_words) // sample_size)
    sample = unique_words[::step][:sample_size]

    md_lower = md_text.lower()
    missing = [w for w in sample if w not in md_lower]
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
    )
