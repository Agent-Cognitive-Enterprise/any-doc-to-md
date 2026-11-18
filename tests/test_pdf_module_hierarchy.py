import json

import fitz

from anydoc2md.format_converters.pdf_converter import convert


def test_module_start_matches_workbook_typography_and_keeps_peer_structure(tmp_path):
    source = tmp_path / "module-start.pdf"
    with fitz.open() as document:
        cover = document.new_page(width=595.276, height=841.89)
        cover.insert_text((50, 160), "BASIC EMERGENCY", fontsize=46)
        cover.insert_text((50, 220), "Approach to the acutely ill and injured", fontsize=18)
        page = document.new_page(width=595.276, height=841.89)
        page.insert_text((85, 110), "The ABCDE and SAMPLE history approach", fontsize=32)
        page.insert_text((85, 180), "Module 1: First approach", fontsize=25)
        page.insert_text((85, 240), "Objectives", fontsize=18)
        page.insert_text((85, 300), "First module body text.", fontsize=12)
        for number in range(4):
            page = document.new_page(width=595.276, height=841.89)
            # Source workbook module-start: 25pt title, then 18pt Objectives;
            # later running copies are 12.22pt in the same top region.
            page.insert_text((85, 28), "Module 2: Approach to trauma", fontsize=25 if number == 0 else 12.22)
            page.insert_text((85, 180), "Objectives", fontsize=18)
            page.insert_text((85, 260), f"Trauma assessment paragraph {number}.", fontsize=12)
            page.insert_text((85, 400), "Figures 1 and 2 present the treatment sequence.", fontsize=18)
        for title in ("TABLE OF CONTENTS: SKILLS", "SKILLS", "GLOSSARY"):
            page = document.new_page(width=595.276, height=841.89)
            page.insert_text((85, 120), title, fontsize=25)
            page.insert_text((85, 180), "Assessment", fontsize=18)
            page.insert_text((85, 260), "Independent section body.", fontsize=12)
        document.save(source)
    output = tmp_path / "output"
    convert(source, output)
    markdown = (output / "index.md").read_text()
    assert markdown.count("Module 2: Approach to trauma") == 1
    assert "## Module 1: First approach" in markdown
    assert "## Module 2: Approach to trauma" in markdown
    assert "### Objectives" in markdown
    for title in ("TABLE OF CONTENTS: SKILLS", "SKILLS", "GLOSSARY"):
        assert f"\n## {title}\n" in markdown
    assert not any(line.startswith("#") and "Figures 1 and 2" in line for line in markdown.splitlines())
    removed = json.loads((output / "removed-blocks.json").read_text())
    assert not any(row["page"] == 3 and row["text"] == "Module 2: Approach to trauma" for row in removed)
    assert sum(row["text"] == "Module 2: Approach to trauma" for row in removed) == 3


def test_smaller_identical_toc_line_is_not_promoted():
    from anydoc2md.format_converters._pdf_blocks import TextBlock
    from anydoc2md.format_converters._pdf_heading_roles import major_numbered_titles
    from anydoc2md.format_converters._pdf_assemble import _fmt_block
    def block(text, size, page):
        return TextBlock(page, (80, 100, 400, 130), text, "heading", size, 0)
    toc = block("Module 2: Trauma", 12, 1)
    one, two = block("Module 1: Assessment", 25, 2), block("Module 2: Trauma", 25, 3)
    ordinary = [block("Objectives", 18, n) for n in range(2, 8)]
    diagram = block("A\nAirway conditions", 29.4, 3)
    promoted = major_numbered_titles([toc, one, two, diagram, *ordinary])
    assert id(diagram) not in promoted
    assert id(toc) not in promoted
    assert id(one) in promoted and id(two) in promoted
    assert _fmt_block(toc, {12: "###"}, promoted) == "### Module 2: Trauma\n"


def test_running_only_headings_do_not_create_a_bogus_section():
    from anydoc2md.format_converters._pdf_blocks import TextBlock
    from anydoc2md.format_converters._pdf_page_furniture import filter_page_furniture
    copies = [TextBlock(n, (70, 10, 180, 25), "Field Guide", "heading", 12, 0,
                        page_height=800, page_width=600) for n in range(1, 6)]
    assert filter_page_furniture(copies, 3) == []
