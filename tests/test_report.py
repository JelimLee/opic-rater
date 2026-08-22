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


def test_assembled_prompts_are_numbered_and_carry_context():
    from opic_rater.rate import assemble, build_context

    prompts = assemble(build_context("## Q1. beach\nI went to the beach."))
    assert sorted(prompts) == [
        "01_function", "02_accuracy", "03_content_context",
        "04_texttype", "05_holistic", "06_synth",
    ]
    for text in prompts.values():
        assert "I went to the beach." in text
        assert "Pronunciation, stress and intonation are NOT evaluable" in text


def test_band_is_read_from_the_trailing_band_line():
    from opic_rater.rate import _extract_band

    assert _extract_band("blah IH blah\nmore text\nBAND: AL") == "AL"
    assert _extract_band("no marker but IM2 appears") == "IM2"
    assert _extract_band("nothing here") == "?"


def test_list_bullet_marker_is_stripped():
    """Regression: an over-escaped regex left a literal '-' inside each <li>."""
    out = _md_to_html("- first item\n- second item")
    assert "<li>first item</li>" in out
    assert "<li>- first item</li>" not in out
    assert out.count("<ul>") == 1
