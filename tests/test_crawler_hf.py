from datetime import date

from crawlers import hf

_PAGE1_HTML = """
<table class="board-table">
<tbody>
<tr class="">
    <td class="b-num-box">2389</td>
    <td class="b-td-left">
        <div class="b-title-box">
            <a data-article-no="600383" href="?mode=view&amp;articleNo=600383&amp;article.offset=0&amp;articleLimit=10">
                주택금융공사, 초록우산어린이재단에 후원금 전달
            </a>
            <div class="b-m-con">
                <span class="b-date">2026-07-24</span>
                <span class="hit">조회수 97</span>
            </div>
        </div>
    </td>
    <td>2026-07-24</td>
    <td class="">97</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_date_and_views(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("offsets", []).append(params["article.offset"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["article.offset"] == 0 else "<table class=\"board-table\"></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hf.requests, "get", fake_get)

    results = hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
    assert captured["offsets"][0] == 0
    assert len(results) == 1
    first = results[0]
    assert first["title"] == "주택금융공사, 초록우산어린이재단에 후원금 전달"
    assert first["url"] == (
        "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
        "?mode=view&articleNo=600383&article.offset=0&articleLimit=10"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 97


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise hf.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(hf.requests, "get", fake_get)

    assert hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(hf.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
