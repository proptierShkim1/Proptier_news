from datetime import date

from crawlers import hug

_ROW1 = """
<tr>
    <td><a href="hsnd000002.jsp?idx=38054"><span class="ico-new"><em class="hide">최근 게시물</em></span>
        부산지역 주거·의료 취약 아동 위한 사업 참여가정 모집</a></td>
    <td>2026.07.27</td>
</tr>
"""
_ROW2 = """
<tr>
    <td><a href="hsnd000002.jsp?idx=38047">AI감사 전문성 강화를 위해 업무협약 체결</a></td>
    <td>2026.07.23</td>
</tr>
"""
_ROW_OLD = """
<tr>
    <td><a href="hsnd000002.jsp?idx=30000">오래된 보도자료</a></td>
    <td>2026.06.01</td>
</tr>
"""


def _table(*rows):
    return f'<table class="tbl-style02"><tbody>{"".join(rows)}</tbody></table>'


def test_fetch_press_releases_parses_title_url_date_and_strips_new_badge(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured.setdefault("row_sizes", []).append(data["rowSize"])
        captured["url"] = url

        class FakeResponse:
            text = _table(_ROW1, _ROW2)
            encoding = "utf-8"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hug.requests, "post", fake_post)

    results = hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000001.jsp"
    assert captured["row_sizes"][0] == 20
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "부산지역 주거·의료 취약 아동 위한 사업 참여가정 모집"
    assert first["url"] == "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000002.jsp?idx=38054"
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-27"
    assert first["view_count"] == 0
    assert results[1]["title"] == "AI감사 전문성 강화를 위해 업무협약 체결"


def test_fetch_press_releases_only_processes_newly_added_rows_across_calls(monkeypatch):
    """rowSize를 늘려도 응답은 처음부터 누적된 전체 목록이므로, 이미 처리한 행을
    다시 처리하면 안 된다."""
    responses = [_table(_ROW1, _ROW2), _table(_ROW1, _ROW2, _ROW_OLD)]

    def fake_post(url, data, headers, timeout):
        idx = 0 if data["rowSize"] == 20 else 1

        class FakeResponse:
            text = responses[idx]
            encoding = "utf-8"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hug.requests, "post", fake_post)

    results = hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_post(url, data, headers, timeout):
        raise hug.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(hug.requests, "post", fake_post)

    assert hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"
        encoding = "utf-8"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(hug.requests, "post", lambda url, data, headers, timeout: FakeResponse())

    assert hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
