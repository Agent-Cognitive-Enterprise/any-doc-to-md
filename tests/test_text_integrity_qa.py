from anydoc2md.output_qa.runner import run_all
from anydoc2md.output_qa.text_integrity import check_text_integrity


def test_localized_corruption_cannot_hide_in_a_long_clean_document(tmp_path):
    text = "Clean instructional paragraph.\n" * 500 + "- \x08\ufffd\ufffd\ufffd\n"
    (tmp_path / "index.md").write_text(text)
    report = run_all(tmp_path)
    check = next(c for c in report.checks if c.name == "text_integrity")
    assert check.status == "warn"
    assert check.severity == "high"
    assert check.details == ["Line 501: U+0008, U+FFFD"]
    assert (tmp_path / "index.md").read_text() == text


def test_unicode_text_layout_and_bidi_marks_are_not_corruption():
    assert check_text_integrity("\u00c9tude \u0412\u043e\u0434\u0430 \u200f\u0645\u0627\u0621\n\t5 mg\r\n").status == "pass"
