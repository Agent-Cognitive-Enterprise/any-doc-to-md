"""Model discovery and size-hint parsing for judge endpoint probing."""

from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    size_hint_b: float | None


def parse_size_hint_billions(model_id: str) -> float | None:
    """
    Best-effort model size parsing from model id.

    Recognizes patterns like:
      - "7b", "13b", "1.5b"
      - "35b-a3b" (returns active size: 3)
      - "8x7b" (returns 56)
    """
    text = model_id.lower()

    def _is_boundary(idx: int) -> bool:
        if idx < 0 or idx >= len(text):
            return True
        return not text[idx].isalnum()

    # MoE hint: 8x7b -> total parameter-ish size 56B.
    for i in range(len(text)):
        if text[i] != "x":
            continue
        # scan left digits (experts)
        left = i - 1
        while left >= 0 and text[left].isdigit():
            left -= 1
        experts_str = text[left + 1 : i]
        if not experts_str:
            continue
        # scan right number (per expert)
        j = i + 1
        while j < len(text) and (text[j].isdigit() or text[j] == "."):
            j += 1
        if j >= len(text) or text[j] != "b":
            continue
        if not _is_boundary(left) or not _is_boundary(j + 1):
            continue
        try:
            experts = int(experts_str)
            per = float(text[i + 1 : j])
        except ValueError:
            continue
        return experts * per

    # Active size hint: a3b, a1.5b, etc. Prefer this for MoE-like ids.
    for i in range(len(text) - 2):
        if text[i] != "a":
            continue
        if not _is_boundary(i - 1):
            continue
        j = i + 1
        while j < len(text) and (text[j].isdigit() or text[j] == "."):
            j += 1
        if j == i + 1:
            continue
        if j >= len(text) or text[j] != "b":
            continue
        if not _is_boundary(j + 1):
            continue
        try:
            return float(text[i + 1 : j])
        except ValueError:
            continue

    # Standard: 7b, 13b, 1.5b
    for i in range(len(text)):
        if not text[i].isdigit():
            continue
        if not _is_boundary(i - 1):
            continue
        j = i
        while j < len(text) and (text[j].isdigit() or text[j] == "."):
            j += 1
        if j >= len(text) or text[j] != "b":
            continue
        if not _is_boundary(j + 1):
            continue
        try:
            return float(text[i:j])
        except ValueError:
            continue

    return None


def fetch_model_ids(judge_url: str, *, timeout_s: int = 10) -> list[str]:
    """
    Fetch model ids from an OpenAI-compatible endpoint.

    Expects GET <judge_url>/models to return either:
      - {"data": [{"id": "..."}, ...]}
      - [{"id": "..."}, ...]
    """
    resp = requests.get(f"{judge_url.rstrip('/')}/models", timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict):
        raw_models = data.get("data", [])
    elif isinstance(data, list):
        raw_models = data
    else:
        raw_models = []

    ids: list[str] = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                ids.append(model_id.strip())

    return sorted(set(ids))

