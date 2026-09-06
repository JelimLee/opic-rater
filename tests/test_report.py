"""Markdown -> HTML rendering for the local report file."""

from opic_rater.report import _md_to_html, to_html


def test_headings_and_bold():
    out = _md_to_html("# Title\n\nsome **bold** text")
    assert "<h1>Title</h1>" in out
    assert "<strong>bold</strong>" in out


def test_table_is_rendered_with_header_row():
    md = "| a | b |\n|---|---|\n| 1 | 2 |"
    out = _md_to_html(md)
    assert out.count("<table>") == 1 and out.count("</table>") == 1
    assert "<th>a</th>" in out and "<td>1</td>" in out


def test_html_escaping_prevents_injection():
    assert "<script>" not in _md_to_html("<script>alert(1)</script>")


def test_to_html_writes_standalone_document(tmp_path):
    p = to_html("# Hi", "T", tmp_path / "r.html")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "<title>T</title>" in text


def test_list_bullet_marker_is_stripped():
    """Regression: an over-escaped regex left a literal '-' inside each <li>."""
    out = _md_to_html("- first item\n- second item")
    assert "<li>first item</li>" in out
    assert "<li>- first item</li>" not in out
    assert out.count("<ul>") == 1
