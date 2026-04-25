"""
Prompt construction and source evidence tests for anydoc2md.llm_judge.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests._llm_judge_helpers import adapter_result, traits

from anydoc2md.format_converters.tournament import source_evidence
from anydoc2md.format_converters.tournament.source_evidence import (
    build_source_evidence_packet,
)
from anydoc2md.llm_judge import (
    EXCERPT_CHARS_PER_ADAPTER,
    _evidence_block,
    _excerpt,
    _traits_summary,
    build_audit_prompt,
    build_prompt,
)


class TestExcerpt:
    def test_short_text_returned_unchanged(self) -> None:
        text = "Hello world"
        assert _excerpt(text) == text

    def test_at_limit_returned_unchanged(self) -> None:
        text = "x" * EXCERPT_CHARS_PER_ADAPTER
        assert _excerpt(text) == text

    def test_long_text_truncated_to_within_budget(self) -> None:
        text = "A" * 20_000
        result = _excerpt(text)
        assert len(result) <= EXCERPT_CHARS_PER_ADAPTER + 200

    def test_long_text_contains_front(self) -> None:
        text = "START_MARKER" + "x" * 10_000 + "END_MARKER"
        result = _excerpt(text)
        assert "START_MARKER" in result

    def test_long_text_contains_end(self) -> None:
        text = "x" * 10_000 + "END_MARKER"
        result = _excerpt(text)
        assert "END_MARKER" in result

    def test_long_text_contains_middle_label(self) -> None:
        text = "x" * 10_000
        result = _excerpt(text)
        assert "middle" in result.lower()


class TestEvidenceBlock:
    def test_contains_adapter_name(self, tmp_path: Path) -> None:
        result = adapter_result("docling", tmp_path, "# Title\n\nSome text.")
        block = _evidence_block(result)
        assert "docling" in block

    def test_contains_stats(self, tmp_path: Path) -> None:
        result = adapter_result("inhouse", tmp_path, "# H\n\nWord " * 50)
        block = _evidence_block(result)
        assert "chars" in block
        assert "words" in block

    def test_contains_markdown_fence(self, tmp_path: Path) -> None:
        result = adapter_result("markitdown", tmp_path, "# Hello")
        block = _evidence_block(result)
        assert "```markdown" in block

    def test_image_count_in_stats(self, tmp_path: Path) -> None:
        md = '<img src="images/a.png" alt="x" width="10" height="10">\n# Title\n'
        result = adapter_result("docling", tmp_path, md)
        block = _evidence_block(result)
        assert "1 image" in block


class TestTraitsSummary:
    def test_scanned_flagged(self) -> None:
        assert "scanned" in _traits_summary(traits(is_scanned=True)).lower()

    def test_image_heavy_flagged(self) -> None:
        assert "image" in _traits_summary(traits(is_image_heavy=True)).lower()

    def test_table_heavy_flagged(self) -> None:
        assert "table" in _traits_summary(traits(is_table_heavy=True)).lower()

    def test_standard_doc_label_when_no_flags(self) -> None:
        assert "standard" in _traits_summary(traits()).lower()

    def test_file_type_present(self) -> None:
        assert "PDF" in _traits_summary(traits(file_type="pdf"))


class TestBuildPrompt:
    def test_returns_two_strings(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        system, user = build_prompt([a, b], traits())
        assert isinstance(system, str) and isinstance(user, str)

    def test_system_contains_json_schema(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        system, _ = build_prompt([a, b], traits())
        assert '"preferred"' in system
        assert '"confidence"' in system
        assert '"violations"' in system

    def test_user_contains_adapter_names(self, tmp_path: Path) -> None:
        a = adapter_result("inhouse", tmp_path, "# In-house")
        b = adapter_result("docling", tmp_path, "# Docling")
        _, user = build_prompt([a, b], traits())
        assert "inhouse" in user
        assert "docling" in user

    def test_user_contains_traits_summary(self, tmp_path: Path) -> None:
        a = adapter_result("a", tmp_path, "# A")
        b = adapter_result("b", tmp_path, "# B")
        _, user = build_prompt([a, b], traits(is_table_heavy=True))
        assert "table" in user.lower()


class TestBuildAuditPrompt:
    def test_contains_source_path_and_candidate_name(self, tmp_path: Path) -> None:
        candidate = adapter_result("inhouse", tmp_path, "# Inhouse")
        audit_pdf = tmp_path / "audit.pdf"
        audit_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        system, user = build_audit_prompt(
            candidate,
            Path("/src/doc.pdf"),
            traits(),
            audit_pdf,
        )
        assert '"preferred"' in system
        assert "Source evidence packet" in user
        assert "Rendered candidate PDF" in user
        assert "inhouse" in user


class TestSourceEvidencePacket:
    def test_text_packet_contains_chunks(self, tmp_path: Path) -> None:
        source = tmp_path / "doc.txt"
        source.write_text("Para one.\n\nPara two.\n\nPara three.", encoding="utf-8")
        packet = build_source_evidence_packet(source, traits(file_type="txt"))
        rendered = packet.to_prompt_text()
        assert "Text chunks" in rendered
        assert "Para one." in rendered

    def test_pdf_packet_contains_page_evidence(self, tmp_path: Path) -> None:
        source = tmp_path / "doc.pdf"
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello from source PDF.")
        doc.save(source)
        doc.close()

        packet = build_source_evidence_packet(source, traits(file_type="pdf", page_count=1))
        rendered = packet.to_prompt_text()
        assert "Page-oriented source evidence" in rendered
        assert "Hello from source PDF." in rendered

    def test_pdf_packet_samples_pages_across_long_document(self, tmp_path: Path) -> None:
        source = tmp_path / "long.pdf"
        import fitz

        doc = fitz.open()
        total_pages = 20
        for page_no in range(1, total_pages + 1):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page marker {page_no}")
        doc.save(source)
        doc.close()

        packet = build_source_evidence_packet(
            source,
            traits(file_type="pdf", page_count=total_pages),
        )
        page_numbers = [page.page_number for page in packet.pages]
        assert page_numbers[0] == 1
        assert page_numbers[-1] == total_pages
        assert page_numbers == sorted(page_numbers)
        assert len(page_numbers) == source_evidence.MAX_SOURCE_PAGES

    def test_text_packet_samples_chunks_across_long_document(self, tmp_path: Path) -> None:
        source = tmp_path / "long.txt"
        total_paragraphs = 30
        source.write_text(
            "\n\n".join(f"Paragraph {index}" for index in range(1, total_paragraphs + 1)),
            encoding="utf-8",
        )
        packet = build_source_evidence_packet(source, traits(file_type="txt"))
        assert packet.text_chunks[0] == "Paragraph 1"
        assert packet.text_chunks[-1] == f"Paragraph {total_paragraphs}"
        assert len(packet.text_chunks) == source_evidence.MAX_TEXT_CHUNKS
        chunk_numbers = [int(chunk.rsplit(" ", 1)[-1]) for chunk in packet.text_chunks]
        assert chunk_numbers == sorted(chunk_numbers)

    def test_pdf_packet_samples_blocks_across_page(self, tmp_path: Path) -> None:
        source = tmp_path / "blocks.pdf"
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        for index in range(1, 11):
            y0 = 50 + (index * 60)
            rect = fitz.Rect(72, y0, 520, y0 + 40)
            page.insert_textbox(rect, f"Block {index}", fontsize=12)
        doc.save(source)
        doc.close()

        packet = build_source_evidence_packet(source, traits(file_type="pdf", page_count=1))
        assert packet.pages
        blocks = packet.pages[0].blocks
        assert len(blocks) == source_evidence.MAX_BLOCKS_PER_PAGE
        assert any("Block 10" in block.text_excerpt for block in blocks)

    def test_persisted_pdf_packet_includes_more_pages_than_prompt_packet(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "persisted.pdf"
        import fitz

        doc = fitz.open()
        total_pages = 20
        for page_no in range(1, total_pages + 1):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page marker {page_no}")
        doc.save(source)
        doc.close()

        document_traits = traits(file_type="pdf", page_count=total_pages)
        prompt_packet = build_source_evidence_packet(source, document_traits)
        persisted_packet = source_evidence.build_persisted_source_evidence_packet(
            source,
            document_traits,
        )

        assert len(prompt_packet.pages) == source_evidence.MAX_SOURCE_PAGES
        assert len(persisted_packet.pages) == total_pages
        assert persisted_packet.pages[0].page_number == 1
        assert persisted_packet.pages[-1].page_number == total_pages

    def test_persisted_text_packet_includes_more_chunks_than_prompt_packet(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "persisted.txt"
        total_paragraphs = 30
        source.write_text(
            "\n\n".join(f"Paragraph {index}" for index in range(1, total_paragraphs + 1)),
            encoding="utf-8",
        )
        document_traits = traits(file_type="txt")
        prompt_packet = build_source_evidence_packet(source, document_traits)
        persisted_packet = source_evidence.build_persisted_source_evidence_packet(
            source,
            document_traits,
        )

        assert len(prompt_packet.text_chunks) == source_evidence.MAX_TEXT_CHUNKS
        assert len(persisted_packet.text_chunks) == total_paragraphs
        assert persisted_packet.text_chunks[0] == "Paragraph 1"
        assert persisted_packet.text_chunks[-1] == f"Paragraph {total_paragraphs}"

    def test_persist_source_evidence_packet_writes_json(self, tmp_path: Path) -> None:
        anydoc2md_dir = tmp_path / ".any-doc-to-md"
        source = tmp_path / "doc.txt"
        source.write_text("Para one.\n\nPara two.", encoding="utf-8")

        written = source_evidence.persist_source_evidence_packet(
            source_path=source,
            traits=traits(file_type="txt"),
            anydoc2md_dir=anydoc2md_dir,
            doc_key="org__doc.txt",
        )
        assert written.exists()
        payload = json.loads(written.read_text(encoding="utf-8"))
        assert payload["format_version"] == 1
        assert payload["source_kind"] == "txt"
        assert payload["text_chunks"]
