from views import firms


def _issue(title="제목", firm="직방", cat="🤖 AI", articles=None):
    return {
        "cat": cat, "cat_bg": "#fff", "cat_fg": "#000", "title": title, "firm": firm,
        "count": 1, "date": "2026-08-11", "live": False,
        "articles": articles or [("2026-08-11 09:00", "기사제목", "https://x/1")],
    }


def test_issue_html_escapes_malicious_title():
    iss = _issue(title="<img src=x onerror=alert(1)>")

    html = firms._issue_html(iss)

    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_issue_html_escapes_malicious_article_title_and_url():
    iss = _issue(articles=[("2026-08-11 09:00", "<script>alert(2)</script>", '"><script>alert(3)</script>')])

    html = firms._issue_html(iss)

    assert "<script>alert(2)</script>" not in html
    assert "<script>alert(3)</script>" not in html
