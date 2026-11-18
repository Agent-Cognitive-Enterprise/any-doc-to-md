"""PDF typography parents/children must survive numbered-family promotion."""
import fitz

from anydoc2md.format_converters.pdf_converter import convert


def headings(markdown):
    return {line.lstrip("# "): len(line) - len(line.lstrip("#"))
            for line in markdown.splitlines() if line.startswith("#")}


def test_larger_parts_remain_parents_of_numbered_chapters(tmp_path):
    source = tmp_path / "parts.pdf"
    with fitz.open() as document:
        for part, numbers in (("ONE: FIELD WORK", (1, 2)), ("TWO: LAB WORK", (3, 4))):
            page = document.new_page()
            page.insert_text((70, 110), f"PART {part}", fontsize=24)
            for row, number in enumerate(numbers):
                y = 190 + row * 230
                page.insert_text((70, y), f"Chapter {number}: Practice", fontsize=18)
                page.insert_text((70, y + 50), "Procedure", fontsize=14)
                page.insert_text((70, y + 90), "Read the procedure carefully before work.", fontsize=10)
                for line in range(6):
                    page.insert_text((70, y + 110 + line * 12), "Additional ordinary body text for this procedure.", fontsize=10)
        document.save(source)
    output = tmp_path / "output"
    convert(source, output)
    levels = headings((output / "index.md").read_text())
    assert levels["PART ONE: FIELD WORK"] == levels["PART TWO: LAB WORK"]
    assert levels["PART TWO: LAB WORK"] < levels["Chapter 3: Practice"]
    assert levels["Chapter 3: Practice"] < levels["Procedure"]


def test_annex_family_does_not_flatten_following_chapter_subheadings(tmp_path):
    source = tmp_path / "annex.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((70, 100), "Introduction", fontsize=18)
        for number, title in enumerate(("Annex 1: Forms", "Annex 2: Tables", "Water safety")):
            y = 180 + number * 190
            page.insert_text((70, y), title, fontsize=18)
            page.insert_text((70, y + 40), "Boiling" if number == 2 else "Instructions", fontsize=14)
            page.insert_text((70, y + 80), "Keep clean water safely covered for later use.", fontsize=10)
            for line in range(6):
                page.insert_text((70, y + 100 + line * 12), "Additional ordinary body text for this procedure.", fontsize=10)
        document.save(source)
    output = tmp_path / "output"
    convert(source, output)
    levels = headings((output / "index.md").read_text())
    assert levels["Annex 1: Forms"] == levels["Annex 2: Tables"] == levels["Water safety"]
    assert levels["Introduction"] == levels["Water safety"] < levels["Boiling"]


def test_recurring_intermediate_parent_keeps_numbered_family_nested(tmp_path):
    # Exercises are >1.2x the typical subheading, so the numbered family is promoted;
    # the recurring Chapter tier must still remain its parent.
    source = tmp_path / "exercises.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((70, 90), "PART A", fontsize=26)
        for chapter, numbers in (("Chapter One", (1, 2)), ("Chapter Two", (3,))):
            if chapter == "Chapter Two":
                page = document.new_page()
            page.insert_text((70, 150), chapter, fontsize=22)
            for row, number in enumerate(numbers):
                y = 220 + row * 260
                page.insert_text((70, y), f"Exercise {number}: Pumps", fontsize=18)
                page.insert_text((70, y + 40), "Steps", fontsize=14)
                for line in range(10):
                    page.insert_text((70, y + 90 + line * 12), "Ordinary body text for this exercise step.", fontsize=10)
        document.save(source)
    output = tmp_path / "output"
    convert(source, output)
    levels = headings((output / "index.md").read_text())
    assert levels["PART A"] < levels["Chapter One"] == levels["Chapter Two"]
    assert levels["Chapter Two"] < levels["Exercise 3: Pumps"] == levels["Exercise 1: Pumps"]
    assert levels["Exercise 1: Pumps"] < levels["Steps"]


def test_one_off_cover_and_diagram_letters_do_not_nest_module_family():
    from anydoc2md.format_converters._pdf_assemble import _build_heading_map
    from anydoc2md.format_converters._pdf_blocks import TextBlock
    from anydoc2md.format_converters._pdf_heading_roles import (
        align_promoted_heading_levels, major_numbered_titles,
    )

    def block(page, text, size, kind="heading"):
        return TextBlock(page, (80, 100, 400, 130), text, kind, size, 0)

    blocks = [block(1, "Module 1: Assessment", 25), block(1, "Objectives", 18),
              block(2, "A", 31), block(2, "B\nBreathing conditions", 29.5),
              block(3, "Module 2: Trauma", 25), block(3, "Objectives", 18),
              block(4, "Quick Cards", 46), block(5, "A", 31),
              block(6, "Module 3: Shock", 25), block(6, "Objectives", 18)]
    promoted = major_numbered_titles(blocks)
    levels = align_promoted_heading_levels(blocks, promoted, _build_heading_map(blocks))
    assert levels[25.0] == "##"
    assert levels[18.0] == "###"
