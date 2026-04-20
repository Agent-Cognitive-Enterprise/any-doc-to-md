from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anydoc2md.format_converters import html_converter


def test_html_converter_copies_local_images(tmp_path: Path) -> None:
    html_dir = tmp_path / "html"
    (html_dir / "images").mkdir(parents=True)
    (html_dir / "images" / "pic.png").write_bytes(b"fake-png-bytes")
    source = html_dir / "doc.html"
    source.write_text(
        """
        <html>
          <head><title>Doc</title></head>
          <body>
            <p>Hello</p>
            <img src="images/pic.png" width="160" alt="Pic">
          </body>
        </html>
        """.strip(),
        encoding="utf-8",
    )

    staging = tmp_path / "staging"
    result = html_converter.convert(source, staging)

    assert result.image_count == 1
    assert not result.warnings
    assert (staging / "index.md").exists()
    assert (staging / "images").is_dir()
    assert len(list((staging / "images").iterdir())) == 1
    md = (staging / "index.md").read_text(encoding="utf-8")
    assert "<img" in md
    assert 'width: 10.0em' in md  # 160px / 16 = 10em


def test_html_converter_blocks_file_outside_html_dir(tmp_path: Path) -> None:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"top-secret")
    source = html_dir / "doc.html"
    source.write_text(
        f'<html><body><img src="{secret.as_uri()}" alt="secret"></body></html>',
        encoding="utf-8",
    )

    staging = tmp_path / "staging"
    result = html_converter.convert(source, staging)

    assert result.image_count == 0
    assert any("outside HTML directory" in w for w in result.warnings)
    md = (staging / "index.md").read_text(encoding="utf-8")
    assert "<img" not in md


def test_html_converter_blocks_localhost_network_images(tmp_path: Path) -> None:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    source = html_dir / "doc.html"
    source.write_text(
        '<html><body><img src="http://127.0.0.1/secret.png" alt="x"></body></html>',
        encoding="utf-8",
    )
    staging = tmp_path / "staging"

    with patch("anydoc2md.format_converters.html_converter.urllib.request.urlopen") as mock_urlopen:
        result = html_converter.convert(source, staging)

    mock_urlopen.assert_not_called()
    assert result.image_count == 0
    assert any("disallowed" in w.lower() for w in result.warnings)
    md = (staging / "index.md").read_text(encoding="utf-8")
    assert "<img" not in md

