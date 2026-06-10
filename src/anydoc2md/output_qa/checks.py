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
from pathlib import Path

from anydoc2md.output_qa.result import CheckResult, issue_metadata
from anydoc2md.paragraph_repair.detector import ends_terminal, looks_row_sliced
from anydoc2md.paragraph_repair.markdown_blocks import split_markdown_blocks
from anydoc2md.paragraph_repair.model import ParagraphRepairSettings
from anydoc2md.paragraph_repair.normalization import collapse_whitespace
from anydoc2md.output_qa.image_refs import (
    extract_image_srcs,
    resolve_local_image_ref,
)
from anydoc2md.output_qa.source_checks import (
    check_image_count_match,
    check_text_coverage,
)

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
            **issue_metadata("formatting_only_minor", "minor", 0.95),
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
        saw_blank = False
        while j < len(lines):
            m2 = re.match(r'^(\d+)\.\s+\S', lines[j])
            if m2:
                value = int(m2.group(1))
                # Two separate lists often restart at 1 after a blank line.
                # Treat that as a new list boundary to avoid false positives.
                if saw_blank and value == 1:
                    break
                run.append(value)
                j += 1
                saw_blank = False
            elif lines[j].strip() == "":
                saw_blank = True
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
            **issue_metadata("reading_order", "major", 0.80),
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
            **issue_metadata("heading_hierarchy", "minor", 0.70),
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
            **issue_metadata("caption_detachment", "major", 0.85),
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
            **issue_metadata("heading_hierarchy", "major", 0.75),
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
            **issue_metadata("formatting_only_minor", "minor", 0.65),
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
            **issue_metadata("duplicated_content", "minor", 0.80),
        )
    return CheckResult(name="no_repeated_headings", layer=1, status="pass",
                       message="No suspiciously repeated headings.")


def check_paragraph_not_row_sliced(
    md_text: str,
    settings: ParagraphRepairSettings | None = None,
) -> CheckResult:
    """Warn when prose looks like visual rows split into Markdown paragraphs.

    Detection uses conservative defaults when ``settings`` is ``None``, which is
    how the tournament always calls it. The warning is a quality-visibility
    signal, so it is deliberately independent of ``--paragraph-repair``:
    running with ``off`` still reports row-sliced prose (it is simply not
    auto-fixed), and tuning repair thresholds does not move this check. The
    optional ``settings`` only lets direct/advanced callers override detection
    thresholds; it is never wired to the repair mode and must not be used to
    gate the warning on whether repair ran.
    """
    blocks = split_markdown_blocks(md_text)
    decision = looks_row_sliced(blocks, settings)
    if not decision.detected:
        return CheckResult(name="paragraph_not_row_sliced", layer=1, status="pass",
                           message="No row-sliced paragraph fragmentation detected.")

    signals = decision.signals
    details = [
        "signals: "
        f"prose_blocks={signals.prose_block_count}; "
        f"short_ratio={signals.short_ratio:.2f}; "
        f"no_terminal_ratio={signals.no_terminal_ratio:.2f}; "
        f"continuation_pair_ratio={signals.continuation_pair_ratio:.2f}; "
        f"longest_continuation_run={signals.longest_continuation_run}"
    ]
    sample_lines = _nonterminal_prose_start_lines(blocks)
    if sample_lines:
        details.append(
            "sample_nonterminal_prose_lines="
            + ",".join(str(line) for line in sample_lines[:5])
        )
    return CheckResult(
        name="paragraph_not_row_sliced",
        layer=1,
        status="warn",
        message="Likely row-sliced paragraph fragmentation detected.",
        details=details,
        **issue_metadata(
            "reading_order",
            "minor",
            _paragraph_fragmentation_confidence(signals),
        ),
    )


def _nonterminal_prose_start_lines(blocks) -> list[int]:
    return [
        block.start_line
        for block in blocks
        if block.is_prose and not ends_terminal(collapse_whitespace(block.text))
    ]


def _paragraph_fragmentation_confidence(signals) -> float:
    signal_strength = (
        signals.short_ratio
        + signals.no_terminal_ratio
        + signals.continuation_pair_ratio
        + signals.lowercase_start_ratio
    ) / 4
    run_bonus = min(signals.longest_continuation_run / 100, 0.10)
    return round(max(0.70, min(0.95, 0.65 + signal_strength * 0.25 + run_bonus)), 2)


def check_images_locally_resolvable(md_text: str, staging_dir: Path) -> CheckResult:
    """
    Every local image reference in the MD must resolve to an existing file in
    staging_dir. Catches write failures and path mismatches.
    """
    missing: list[str] = []
    for src in extract_image_srcs(md_text):
        _path, reason = resolve_local_image_ref(staging_dir, src)
        if reason is not None:
            missing.append(reason)
    if missing:
        return CheckResult(
            name="images_locally_resolvable", layer=1, status="fail",
            message=f"{len(missing)} image(s) referenced in MD but missing on disk.",
            details=missing[:5],
            **issue_metadata("orphan_image", "major", 0.95),
        )
    return CheckResult(name="images_locally_resolvable", layer=1, status="pass",
                       message="All referenced images exist on disk.")
