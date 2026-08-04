from datetime import datetime, timedelta

import pytest

from crawlers import naver_news_api


def _set_credentials(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_parses_and_strips_bold_tags_and_prefers_originallink(monkeypatch):
    _set_credentials(monkeypatch)
    payload = {
        "items": [
            {
                "title": "<b>프롭티어</b> 전세사기 예방 서비스 출시",
                "originallink": "https://example.com/news/1",
                "link": "https://news.naver.com/1",
                "description": "<b>프롭티어</b>가 전세사기 예방 서비스를 출시했다.",
                "pubDate": "Mon, 03 Aug 2026 09:00:00 +0900",
            }
        ]
    }
    monkeypatch.setattr(
        naver_news_api.requests, "get",
        lambda url, params, headers, timeout: _FakeResponse(payload),
    )

    results = naver_news_api.search("프롭티어")

    assert results == [{
        "source_detail": "뉴스",
        "title": "프롭티어 전세사기 예방 서비스 출시",
        "url": "https://example.com/news/1",
        "snippet": "프롭티어가 전세사기 예방 서비스를 출시했다.",
        "posted_at": "2026.08.03",
    }]


def test_search_decodes_html_entities_in_title_and_description(monkeypatch):
    _set_credentials(monkeypatch)
    payload = {
        "items": [
            {
                "title": "<b>프롭티어</b> &quot;전세사기 예방&quot; 서비스 출시",
                "originallink": "https://example.com/news/2",
                "link": "https://news.naver.com/2",
                "description": "프롭티어 &amp; 파트너사가 공동 출시",
                "pubDate": "Mon, 03 Aug 2026 09:00:00 +0900",
            }
        ]
    }
    monkeypatch.setattr(
        naver_news_api.requests, "get",
        lambda url, params, headers, timeout: _FakeResponse(payload),
    )

    results = naver_news_api.search("프롭티어")

    assert results[0]["title"] == '프롭티어 "전세사기 예방" 서비스 출시'
    assert results[0]["snippet"] == "프롭티어 & 파트너사가 공동 출시"


def test_search_falls_back_to_link_when_originallink_missing(monkeypatch):
    _set_credentials(monkeypatch)
    payload = {"items": [{
        "title": "제목", "link": "https://news.naver.com/1",
        "description": "요약", "pubDate": "Mon, 03 Aug 2026 09:00:00 +0900",
    }]}
    monkeypatch.setattr(
        naver_news_api.requests, "get",
        lambda url, params, headers, timeout: _FakeResponse(payload),
    )

    results = naver_news_api.search("프롭티어")

    assert results[0]["url"] == "https://news.naver.com/1"


def test_search_sends_client_credentials_and_query_in_request(monkeypatch):
    _set_credentials(monkeypatch)
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _FakeResponse({"items": []})

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    naver_news_api.search("프롭티어")

    assert captured["url"] == "https://openapi.naver.com/v1/search/news.json"
    assert captured["headers"]["X-Naver-Client-Id"] == "test-id"
    assert captured["headers"]["X-Naver-Client-Secret"] == "test-secret"
    assert captured["params"]["query"] == "프롭티어"


def test_search_raises_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        naver_news_api.search("프롭티어")


def test_search_propagates_request_exception(monkeypatch):
    _set_credentials(monkeypatch)

    def fake_get(url, params, headers, timeout):
        raise naver_news_api.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    with pytest.raises(naver_news_api.requests.exceptions.RequestException):
        naver_news_api.search("프롭티어")


def _item(n, pub_date):
    return {
        "title": f"제목{n}",
        "originallink": f"https://example.com/news/{n}",
        "description": f"요약{n}",
        "pubDate": pub_date,
    }


def _rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")


def test_search_paginates_using_start_param_when_max_pages_greater_than_one(monkeypatch):
    _set_credentials(monkeypatch)
    now = datetime.now()
    page1_items = [_item(i, _rfc822(now)) for i in range(naver_news_api._DISPLAY)]
    page2_items = [_item(200, _rfc822(now))]
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["start"])
        if params["start"] == 1:
            return _FakeResponse({"items": page1_items})
        return _FakeResponse({"items": page2_items})

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    results = naver_news_api.search("프롭티어", max_pages=2)

    assert calls == [1, 101]
    assert len(results) == naver_news_api._DISPLAY + 1


def test_search_stops_paging_once_recency_days_cutoff_reached(monkeypatch):
    _set_credentials(monkeypatch)
    now = datetime.now()
    old_date = now - timedelta(days=40)
    page1_items = [_item(1, _rfc822(now)), _item(2, _rfc822(old_date)), _item(3, _rfc822(now))]
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["start"])
        return _FakeResponse({"items": page1_items})

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    results = naver_news_api.search("프롭티어", max_pages=5, recency_days=30)

    assert calls == [1]
    assert len(results) == 1
    assert results[0]["title"] == "제목1"


def test_search_default_call_still_sends_only_start_1_no_recency_filter(monkeypatch):
    """max_pages/recency_days를 안 주면 기존과 동일하게 단일 호출, 필터 없음."""
    _set_credentials(monkeypatch)
    old_date = datetime.now() - timedelta(days=400)
    payload = {"items": [_item(1, _rfc822(old_date))]}
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["start"])
        return _FakeResponse(payload)

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    results = naver_news_api.search("프롭티어")

    assert calls == [1]
    assert len(results) == 1
