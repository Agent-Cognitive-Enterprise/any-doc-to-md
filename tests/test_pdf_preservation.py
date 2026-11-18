from io import BytesIO
import json
from pathlib import Path
import tomllib

import fitz
from PIL import Image

from anydoc2md.format_converters import pdf_converter


def test_default_preserves_short_headings_labels_units_and_quantities(tmp_path):
    import json
    source = tmp_path / "short.pdf"
    with fitz.open() as doc:
        for number in range(1, 5):
            page = doc.new_page()
            page.insert_text((72, 28), f"Step {number}")
            page.insert_text((72, 65), "5")
            page.insert_text((72, 300), "WARNING")
            page.insert_text((72, 350), "\u00b5g")
            page.insert_text((72, 450), "5")
            page.insert_text((72, 500), "+")
            page.insert_text((72, 550), ".")
            page.insert_text((295, 820), str(number))
            page.insert_text((72, 400), "Long body text remains available.")
        doc.save(source)
    output = tmp_path / "output"
    pdf_converter.convert(source, output)
    rows = json.loads((output / "removed-blocks.json").read_text(encoding="utf-8"))
    assert len(rows) == 8
    assert sum(r["reason"] == "isolated decorative punctuation" for r in rows) == 4
    text = (output / "index.md").read_text(encoding="utf-8")
    for label in ["\u00b5g", "WARNING", "Step 1", "Step 2", "Step 3", "Step 4", "5", "+"]:
        assert label in text
    assert text.count("5") >= 8
    # A second conversion must replace, not accumulate, extraction diagnostics.
    pdf_converter.convert(source, output)
    assert len(json.loads((output / "removed-blocks.json").read_text(encoding="utf-8"))) == 8


def test_corrupt_pdf_image_is_skipped_with_structured_diagnostics(tmp_path, monkeypatch):
    import json
    from anydoc2md.format_converters import _pdf_extract
    class Document:
        def extract_image(self, xref):
            return {"image": b"corrupt", "ext": "jpx"}
    class Page:
        def get_images(self, full):
            return [(7,)]
    images = tmp_path / "images"
    images.mkdir()
    monkeypatch.setattr(_pdf_extract.fitz, "Pixmap", lambda *args: (_ for _ in ()).throw(ValueError("bad codec")))
    result = _pdf_extract._extract_page_images(
        doc=Document(), page=Page(), page_num=2, images_dir=images,
        page_width=600, column_split_ratio=.55, seen_hashes=set(),
    )
    assert result == []
    assert json.loads((tmp_path / "skipped-images.json").read_text(encoding="utf-8")) == [
        {"page": 2, "xref": 7, "reason": "bad codec"}
    ]


def test_numbered_headings_and_unit_differences_survive(tmp_path):
    source = tmp_path / "body.pdf"
    units = ["ml", "cl", "mm", "mild"]
    with fitz.open() as doc:
        for number, unit in enumerate(units, 1):
            page = doc.new_page()
            page.insert_text((72, 28), f"Step {number}")
            page.insert_text((72, 815), f"Total: {number * 5} {unit}")
        doc.save(source)
    pdf_converter.convert(source, tmp_path / "output", overrides={"min_text_len": 1})
    text = (tmp_path / "output/index.md").read_text(encoding="utf-8")
    for number, unit in enumerate(units, 1):
        assert f"Step {number}" in text
        assert f"Total: {number * 5} {unit}" in text
    assert (tmp_path / "output/removed-blocks.json").read_text(encoding="utf-8").strip() == "[]"


def test_jpeg2000_is_published_as_renderable_png(tmp_path):
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "red").save(buffer, format="JPEG2000")
    source = tmp_path / "codec.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "A local image conversion regression.")
        page.insert_image(fitz.Rect(72, 100, 172, 200), stream=buffer.getvalue())
        doc.save(source)
    result = pdf_converter.convert(source, tmp_path / "output")
    assert result.image_count == 1
    image = next((tmp_path / "output/images").iterdir())
    assert image.suffix == ".png"
    with Image.open(image) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (20, 20)


def test_repeated_margin_headers_and_numbered_footers_are_removed_and_audited(tmp_path):
    source = tmp_path / "furniture.pdf"
    with fitz.open() as doc:
        for number in range(1, 5):
            page = doc.new_page()
            page.insert_text((72, 28), "Irrigation manual")
            page.insert_text((72, 48), "Module 13 - Irrigation Manual")
            page.insert_text((72, 815), f"{number} - Module 13")
            page.insert_text((72, 300), "Repeated body advice must remain available.")
            page.insert_text((72, 400), f"Unique content for section {number}.")
        doc.save(source)
    pdf_converter.convert(source, tmp_path / "output")
    text = (tmp_path / "output/index.md").read_text(encoding="utf-8")
    assert "Irrigation manual" not in text
    assert "Module 13 - Irrigation Manual" not in text
    for number in range(1, 5):
        assert f"{number} - Module 13" not in text
    assert text.count("Repeated body advice") == 4
    assert "Unique content for section 4" in text
    rows = json.loads((tmp_path / "output/removed-blocks.json").read_text())
    assert {row["page"] for row in rows} == {1, 2, 3, 4}
    assert all(row["text"] and row["bbox"] and row["signature"] for row in rows)
    pdf_converter.convert(source, tmp_path / "output", overrides={"running_header_min_pages": 5})
    assert json.loads((tmp_path / "output/removed-blocks.json").read_text()) == []


def test_default_audits_repeated_edge_headings_and_sequential_numbers(tmp_path):
    source = tmp_path / "edge-content.pdf"
    with fitz.open() as doc:
        for number in range(1, 5):
            page = doc.new_page()
            page.insert_text((72, 55), "WARNING", fontsize=18)
            page.insert_text((72, 28), "Module 13")
            page.insert_text((295, 820), "5")
            page.insert_text((295, 28), str(number))
            page.insert_text((72, 785), "Repeated bottom body heading", fontsize=18)
            page.insert_text((72, 300), f"Body for section {number}.")
        doc.save(source)
    output = tmp_path / "output"
    pdf_converter.convert(source, output)
    text = (output / "index.md").read_text()
    for heading in ("WARNING", "Module 13", "Repeated bottom body heading"):
        assert text.count(heading) == 0
    for number in range(1, 5):
        assert f"\n{number}\n" not in text
    assert text.count("\n5\n") == 4
    rows = json.loads((output / "removed-blocks.json").read_text())
    assert len(rows) == 16
    assert all(row["reason"] == "repeated edge furniture" for row in rows)


def test_explicit_sequential_page_labels_are_audited_but_body_labels_survive(tmp_path):
    source = tmp_path / "pages.pdf"
    with fitz.open() as doc:
        for number in range(1, 5):
            page = doc.new_page()
            page.insert_text((72, 820), f"Page {number} of 4")
            page.insert_text((72, 300), "Page 2 of 4")
        doc.save(source)
    output = tmp_path / "output"
    pdf_converter.convert(source, output)
    text = (output / "index.md").read_text()
    assert text.count("Page 2 of 4") == 4
    rows = json.loads((output / "removed-blocks.json").read_text())
    assert [row["text"] for row in rows] == [f"Page {n} of 4" for n in range(1, 5)]
    pdf_converter.convert(source, output, overrides={"running_header_min_pages": 5})
    assert json.loads((output / "removed-blocks.json").read_text()) == []


def test_pdf_length_override_is_explicit_and_audited(tmp_path):
    source = tmp_path / "override.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 300), "WARNING")
        doc.save(source)
    output = tmp_path / "output"
    pdf_converter.convert(source, output, overrides={"min_text_len": 10})
    assert "WARNING" not in (output / "index.md").read_text()
    rows = json.loads((output / "removed-blocks.json").read_text())
    assert rows[0]["text"] == "WARNING"
    assert rows[0]["reason"] == "below min_text_len"
    assert rows[0]["threshold"] == 10


def test_side_navigation_is_audited_without_removing_body_labels(tmp_path):
    source = tmp_path / "navigation.pdf"
    with fitz.open() as doc:
        for number in range(1, 5):
            page = doc.new_page()
            page.insert_text((570, 130), "INTRO", fontsize=6, rotate=90)
            page.insert_text((72, 300), "INTRO")
            page.insert_text((72, 28), f"Step {number}")
            page.insert_text((72, 815), f"Total: {number * 5} {'ml' if number % 2 else 'cl'}")
        doc.save(source)
    output = tmp_path / "output"
    pdf_converter.convert(source, output)
    rows = json.loads((output / "removed-blocks.json").read_text())
    assert len(rows) == 4
    assert all(row["text"] == "INTRO" and row["signature"][0] == "right" for row in rows)
    text = (output / "index.md").read_text()
    assert text.count("INTRO") == 4
    assert "Step 4" in text and "Total: 20 cl" in text


def test_release_version_and_changelog_are_consistent():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert project["project"]["version"] == "0.3.0"
    changelog = (root / "CHANGELOG.md").read_text()
    assert "## 0.2.0" not in changelog
    assert "## 0.2.1" not in changelog
    assert "## 0.3.0" in changelog
    assert "## 0.1.4" not in changelog
    latest = changelog.split("## 0.3.0", 1)[1].split("## 0.1.3", 1)[0]
    assert "### Added" in latest
    assert "### Changed" in latest
    assert "### Fixed" in latest
