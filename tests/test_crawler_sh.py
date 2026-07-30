from datetime import date

from crawlers import sh

_PAGE1_HTML = """
<table>
<tbody>
<tr>
    <td>1469</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('307210');return false;">
        서울주택도시개발공사 방치된 반지하 주택 공유 창고로 활용</a></td>
    <td>홍보부</td>
    <td class="num">2026-07-20</td>
    <td class="num">223</td>
</tr>
<tr>
    <td>1468</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('307029');return false;">
        서울주택도시개발공사 폭염 대비 건설 현장 안전 점검 실시</a></td>
    <td>홍보부</td>
    <td class="num">2026-07-15</td>
    <td class="num">102</td>
</tr>
</tbody>
</table>
"""

_PAGE2_HTML = """
<table>
<tbody>
<tr>
    <td>1400</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('300000');return false;">
        오래된 보도자료</a></td>
    <td>홍보부</td>
    <td class="num">2026-06-01</td>
    <td class="num">1</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_department_date_and_views(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("pages", []).append(params["page"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["page"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    results = sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139/list.do"
    assert captured["pages"][0] == 1
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "서울주택도시개발공사 방치된 반지하 주택 공유 창고로 활용"
    assert first["url"] == (
        "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139/view.do?seq=307210&page=1"
    )
    assert first["department"] == "홍보부"
    assert first["announced_at"] == "2026-07-20"
    assert first["view_count"] == 223


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["page"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    results = sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise sh.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(sh.requests, "get", fake_get)

    assert sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(sh.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
