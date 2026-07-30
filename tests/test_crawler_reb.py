from datetime import date

from crawlers import reb

_PAGE1_HTML = """
<table>
  <thead><tr><th>번호</th><th>제목</th><th>등록일</th><th>조회</th><th>첨부</th></tr></thead>
  <tbody>
    <tr>
      <td>1910</td>
      <td class="al mBlock"><a href="javascript:" data-id="115796" class="nttInfoBtn">
        한국부동산원, 한국토지보상법연구회와 공동 학술세미나 개최</a></td>
      <td>2026.07.27.</td>
      <td>4</td>
      <td></td>
    </tr>
    <tr>
      <td>1909</td>
      <td class="al mBlock"><a href="javascript:" data-id="115757" class="nttInfoBtn">
        주간아파트가격동향(20260720기준)</a></td>
      <td>2026.07.23.</td>
      <td>1958</td>
      <td></td>
    </tr>
  </tbody>
</table>
"""

_PAGE2_HTML = """
<table>
  <thead><tr><th>번호</th><th>제목</th><th>등록일</th><th>조회</th><th>첨부</th></tr></thead>
  <tbody>
    <tr>
      <td>1900</td>
      <td class="al mBlock"><a href="javascript:" data-id="114918" class="nttInfoBtn">
        오래된 보도자료</a></td>
      <td>2026.06.01.</td>
      <td>10</td>
      <td></td>
    </tr>
  </tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_date_and_views(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured.setdefault("calls", []).append(data["currPage"])
        captured["url"] = url
        captured["data"] = data

        class FakeResponse:
            text = _PAGE1_HTML if data["currPage"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(reb.requests, "post", fake_post)

    results = reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.reb.or.kr/reb/na/ntt/selectNttList.do"
    assert captured["data"]["mi"] == "9565"
    assert captured["data"]["bbsId"] == "1154"
    assert captured["calls"][0] == 1
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "한국부동산원, 한국토지보상법연구회와 공동 학술세미나 개최"
    assert first["url"] == (
        "https://www.reb.or.kr/reb/na/ntt/selectNttInfo.do?mi=9565&bbsId=1154&nttSn=115796"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-27"
    assert first["view_count"] == 4


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_post(url, data, headers, timeout):
        class FakeResponse:
            text = pages[data["currPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(reb.requests, "post", fake_post)

    results = reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_post(url, data, headers, timeout):
        raise reb.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(reb.requests, "post", fake_post)

    assert reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(reb.requests, "post", lambda url, data, headers, timeout: FakeResponse())

    assert reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
