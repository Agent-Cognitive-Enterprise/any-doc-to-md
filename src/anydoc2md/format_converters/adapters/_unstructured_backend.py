"""Subprocess backend for the optional Unstructured adapter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from anydoc2md.format_converters.adapters._unstructured_markdown import (
    render_elements_to_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--images-dir", required=True)
    args = parser.parse_args(argv)

    try:
        from unstructured.partition.auto import partition
    except ModuleNotFoundError:
        print(
            "unstructured package not installed. Install with: "
            "pip install 'unstructured[all-docs]' and required system dependencies.",
            file=sys.stderr,
        )
        return 2

    input_path = Path(args.input)
    output_path = Path(args.output)
    images_dir = Path(args.images_dir)

    try:
        elements = partition(
            filename=str(input_path),
            include_page_breaks=True,
        )
        markdown = render_elements_to_markdown(elements)
    except Exception as exc:
        print(f"unstructured conversion failed: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
