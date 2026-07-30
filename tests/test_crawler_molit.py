from datetime import date

from crawlers import molit

_SAMPLE_HTML = """
<table class="table line_no bd_tbl bd_tbl_ul">
  <tr><th>번호</th><th>제목</th><th>분류</th><th>등록일</th><th>조회수</th></tr>
  <tr>
    <td>834</td>
    <td><a href="dtl.jsp?lcmspage=1&id=95092253">스마트도시산업 통계 특수분류 제정</a></td>
    <td>국토도시</td>
    <td>2026-07-24</td>
    <td>512</td>
  </tr>
  <tr>
    <td>833</td>
    <td><a href="dtl.jsp?lcmspage=1&id=95092252">'26년 상반기 전국 지가 1.22% 상승</a></td>
    <td>주택토지</td>
    <td>2026-07-23</td>
    <td>836</td>
  </tr>
</table>
"""


def test_fetch_press_releases_parses_title_url_department_date_and_views(monkeypatch):
    class FakeResponse:
        text = _SAMPLE_HTML

        def raise_for_status(self):
            pass

    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(molit.requests, "get", fake_get)

    results = molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24))

    assert captured["url"] == "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
    assert captured["params"]["search_regdate_s"] == "2026-06-24"
    assert captured["params"]["search_regdate_e"] == "2026-07-24"
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "스마트도시산업 통계 특수분류 제정"
    assert first["url"] == "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?lcmspage=1&id=95092253"
    assert first["department"] == "국토도시"
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 512


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise molit.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(molit.requests, "get", fake_get)

    assert molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(molit.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24)) == []
