from datetime import date

from crawlers import seoul_opengov

_PAGE1_HTML = """
<table>
<thead><tr><th>번호</th><th>제목</th><th>부서</th><th>등록일</th><th>조회</th></tr></thead>
<tbody>
<tr>
    <td class="data-num">46038</td>
    <td class="data-title aLeft"><a href="/press/36601374">제14차정비사업통합심의위원회개최결과</a></td>
    <td class="data-dept">주택실주거정비과</td>
    <td class="data-date">2026-07-24</td>
    <td class="data-hit">46</td>
</tr>
<tr>
    <td class="data-num">46036</td>
    <td class="data-title aLeft"><a href="/press/36601376">상담사지키고상담품질높인다</a></td>
    <td class="data-dept">서울시120다산콜재단</td>
    <td class="data-date">2026-07-24</td>
    <td class="data-hit">24</td>
</tr>
</tbody>
</table>
"""

_PAGE2_HTML = """
<table>
<tbody>
<tr>
    <td class="data-num">46000</td>
    <td class="data-title aLeft"><a href="/press/36500000">오래된주택정책보도자료</a></td>
    <td class="data-dept">주택실주택정책과</td>
    <td class="data-date">2026-06-01</td>
    <td class="data-hit">5</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_keeps_only_relevant_departments(monkeypatch):
    def fake_get(url, params, headers, timeout):
        captured.setdefault("calls", []).append(params["page"])

        class FakeResponse:
            text = _PAGE1_HTML if params["page"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    captured = {}
    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    results = seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 1
    first = results[0]
    assert first["title"] == "제14차정비사업통합심의위원회개최결과"
    assert first["url"] == "https://opengov.seoul.go.kr/press/36601374"
    assert first["department"] == "주택실주거정비과"
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 46


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["page"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    results = seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 1
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise seoul_opengov.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    assert seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        seoul_opengov.requests, "get", lambda url, params, headers, timeout: FakeResponse()
    )

    assert seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
