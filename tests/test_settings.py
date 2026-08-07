from views.settings import _escape_html_attr


def test_escape_html_attr_escapes_double_quotes():
    assert _escape_html_attr('제목 "인용문" 포함') == "제목 &quot;인용문&quot; 포함"


def test_escape_html_attr_escapes_angle_brackets():
    assert _escape_html_attr("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_escape_html_attr_escapes_ampersand_before_other_entities():
    assert _escape_html_attr("A & B < C") == "A &amp; B &lt; C"


def test_escape_html_attr_escapes_raw_ampersand_in_entity_like_text():
    """입력은 이미 이스케이프된 HTML이 아니라 순수 텍스트로 취급한다 — '&lt;'라는 문자열
    자체가 원문에 있었다면 '&'만 이스케이프해서 '&amp;lt;'가 되는 게 맞다."""
    assert _escape_html_attr("&lt;") == "&amp;lt;"
