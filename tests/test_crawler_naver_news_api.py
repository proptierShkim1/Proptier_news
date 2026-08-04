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
