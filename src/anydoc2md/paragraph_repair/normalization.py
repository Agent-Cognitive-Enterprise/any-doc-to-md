"""Shared whitespace-normalization primitives for paragraph repair.

The paragraph-repair modules use two distinct normalizations, kept here so they
cannot drift apart:

- `collapse_whitespace` folds every run of whitespace into a single space and
  strips the ends. It is used wherever block text is compared or measured as a
  single logical line (length checks, continuation heuristics, scoring).
- `strip_whitespace` removes whitespace entirely, producing a content
  fingerprint for loss checks. Two texts with the same fingerprint differ only
  in whitespace, so no non-whitespace character was dropped, added, or rewritten.
"""
from __future__ import annotations


def collapse_whitespace(text: str) -> str:
    """Fold all whitespace runs into single spaces and strip the ends."""
    return " ".join(text.split())


def strip_whitespace(text: str) -> str:
    """Remove all whitespace, yielding a content fingerprint for loss checks."""
    return "".join(text.split())
