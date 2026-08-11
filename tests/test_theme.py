import theme


def _news_item(title="제목", url="https://x/1", desc=None, decision=None):
    return {
        "signal": "🤖 AI", "title": title, "url": url, "score": 10,
        "desc": desc or ["설명"], "decision": decision or ["이유"],
        "meta": "🕒 2026-08-11 · 네이버",
    }


def test_news_card_html_escapes_malicious_title():
    item = _news_item(title="<img src=x onerror=alert(1)>")

    html = theme._news_card_html(item, "1위")

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_news_card_html_escapes_malicious_url_and_desc():
    item = _news_item(url='https://x/"><script>alert(1)</script>', desc=['<script>alert(2)</script>'])

    html = theme._news_card_html(item, "1위")

    assert "<script>alert(1)</script>" not in html
    assert "<script>alert(2)</script>" not in html


def _policy_item(title="제목", url="https://x/1", source="국토교통부", department="주택정책과"):
    return {
        "signal": "🏛️ 정책", "title": title, "url": url, "score": 10,
        "source": source, "department": department, "view_count": 100, "announced_at": "2026-08-11",
    }


def test_policy_signal_card_html_escapes_malicious_title():
    item = _policy_item(title="<img src=x onerror=alert(1)>")

    html = theme._policy_signal_card_html(item, "1위")

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
