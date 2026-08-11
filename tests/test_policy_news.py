from views import policy_news


def _top(title="제목", url="https://x/1", source="국토교통부", department="주택정책과", view_count=10):
    return {
        "title": title, "url": url, "source": source, "department": department, "view_count": view_count,
    }


def test_brief_lead_html_escapes_malicious_title_and_url():
    top = _top(title="<img src=x onerror=alert(1)>", url='"><script>alert(2)</script>')

    html = policy_news._brief_lead_html(top)

    assert "<img src=x onerror=alert(1)>" not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_brief_lead_html_escapes_malicious_source_and_department():
    top = _top(source="<script>alert(3)</script>", department="<script>alert(4)</script>")

    html = policy_news._brief_lead_html(top)

    assert "<script>alert(3)</script>" not in html
    assert "<script>alert(4)</script>" not in html
