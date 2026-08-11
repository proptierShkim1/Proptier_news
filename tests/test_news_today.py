from views import news_today


def _top(title="제목", url="https://x/1", desc=None, decision=None):
    return {
        "title": title, "url": url,
        "desc": desc or ["설명"], "decision": decision or ["이유"],
    }


def test_brief_lead_html_escapes_malicious_title_and_url():
    top = _top(title="<img src=x onerror=alert(1)>", url='"><script>alert(2)</script>')

    html = news_today._brief_lead_html(top)

    assert "<img src=x onerror=alert(1)>" not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_brief_lead_html_escapes_malicious_desc_and_decision():
    top = _top(desc=["<script>alert(3)</script>"], decision=["<script>alert(4)</script>"])

    html = news_today._brief_lead_html(top)

    assert "<script>alert(3)</script>" not in html
    assert "<script>alert(4)</script>" not in html
