from crawlers import mk_news_api


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _item(art_id=1, title="기사 제목", subtitle="기사 부제목", text="", date_str="2026-01-28T17:55:21+09:00"):
    return {
        "id": 8319682, "score": 0.26, "title": title, "subtitle": subtitle,
        "text": text, "date": date_str, "art_id": str(art_id),
        "stock_codes": None, "keywords": None,
    }


def test_search_extracts_summary_and_body_and_synthesizes_url(monkeypatch):
    text = "[TITLE] 제목 [SUBTITLE] 부제목 [SUMMARY] 요약 내용입니다 [BODY] 본문 내용입니다"
    payload = {"results": [_item(art_id=42, text=text)]}
    monkeypatch.setattr(
        mk_news_api.requests, "post",
        lambda url, json, headers, timeout: _FakeResponse(payload),
    )

    results = mk_news_api.search("프롭티어")

    assert results == [{
        "source_detail": "매경뉴스",
        "title": "기사 제목",
        "url": "mk-api:42",
        "snippet": "요약 내용입니다",
        "posted_at": "2026.01.28",
        "content": "본문 내용입니다",
    }]


def test_search_falls_back_to_subtitle_when_no_summary_tag(monkeypatch):
    payload = {"results": [_item(text="본문만 있음, 태그 없음")]}
    monkeypatch.setattr(
        mk_news_api.requests, "post",
        lambda url, json, headers, timeout: _FakeResponse(payload),
    )

    results = mk_news_api.search("프롭티어")

    assert results[0]["snippet"] == "기사 부제목"
    assert results[0]["content"] == ""


def test_search_skips_items_missing_title_or_art_id(monkeypatch):
    payload = {"results": [
        {**_item(), "title": ""},
        {**_item(), "art_id": None},
        _item(art_id=7),
    ]}
    monkeypatch.setattr(
        mk_news_api.requests, "post",
        lambda url, json, headers, timeout: _FakeResponse(payload),
    )

    results = mk_news_api.search("프롭티어")

    assert len(results) == 1
    assert results[0]["url"] == "mk-api:7"


def test_search_sends_query_and_media_codes_filter_no_date_params_by_default(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse({"results": []})

    monkeypatch.setattr(mk_news_api.requests, "post", fake_post)

    mk_news_api.search("프롭티어")

    assert captured["url"] == "https://api.mk-agents.com/search/vector/filtered"
    assert captured["headers"] == {"Content-Type": "application/json"}
    assert captured["json"]["query"] == "프롭티어"
    assert captured["json"]["limit"] == mk_news_api._LIMIT
    assert captured["json"]["filters"] == {"media_codes": ["82"]}
    assert "date_from" not in captured["json"]
    assert "date_end" not in captured["json"]


def test_search_propagates_request_exception(monkeypatch):
    def fake_post(url, json, headers, timeout):
        raise mk_news_api.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mk_news_api.requests, "post", fake_post)

    try:
        mk_news_api.search("프롭티어")
        assert False, "should have raised"
    except mk_news_api.requests.exceptions.RequestException:
        pass


def test_search_with_recency_days_splits_into_date_windows_and_aggregates(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((json.get("date_from"), json.get("date_end"), json["limit"]))
        return _FakeResponse({"results": [_item(art_id=len(calls))]})

    monkeypatch.setattr(mk_news_api.requests, "post", fake_post)

    results = mk_news_api.search("프롭티어", max_pages=3, recency_days=9)

    assert len(calls) == 3
    for date_from, date_end, limit in calls:
        assert date_from is not None and date_end is not None
        assert limit == mk_news_api._BACKFILL_LIMIT
    # 구간들이 겹치지 않고 최신 → 과거 순으로 이어져야 한다
    assert calls[0][1] > calls[1][1] > calls[2][1]
    assert len(results) == 3


def test_search_with_recency_days_smaller_than_max_pages_stops_early(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json.get("date_from"))
        return _FakeResponse({"results": []})

    monkeypatch.setattr(mk_news_api.requests, "post", fake_post)

    mk_news_api.search("프롭티어", max_pages=10, recency_days=3)

    assert len(calls) == 3
