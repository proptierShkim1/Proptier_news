import notify


def _content(**overrides):
    base = {
        "channel_counts": {},
        "channel_top_news": {},
        "own_brand_news": [],
        "competitor_news": [],
        "market_news": [],
        "total_count": 0,
    }
    base.update(overrides)
    return base


def test_build_adaptive_card_wraps_as_teams_message():
    payload = notify.build_adaptive_card(_content(), "2026-08-27")

    assert payload["type"] == "message"
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_build_adaptive_card_shows_no_items_message_when_total_count_zero():
    payload = notify.build_adaptive_card(_content(total_count=0), "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "없습니다" in body_text


def test_build_adaptive_card_includes_total_count():
    payload = notify.build_adaptive_card(_content(total_count=12), "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "12" in body_text


def test_build_adaptive_card_includes_own_brand_news_titles():
    content = _content(
        total_count=1,
        own_brand_news=[{
            "title": "프롭티어, AI 서비스 출시", "url": "https://x/1", "brand": "프롭티어",
            "channel": "네이버", "posted_at": "", "signal": "🚀", "desc": "",
        }],
    )
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "프롭티어, AI 서비스 출시" in body_text


def test_build_adaptive_card_uses_briefing_archive_section_titles():
    """브리핑 아카이브 화면(views/briefings.py._render_sections)과 동일한 섹션 제목을
    써야 한다 — 사용자가 "팀즈로 보내는 내용도 브리핑 아카이브처럼" 보내달라고 요청."""
    content = _content(
        total_count=1,
        own_brand_news=[{
            "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
            "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀", "desc": "",
        }],
        competitor_news=[{
            "title": "경쟁사뉴스", "url": "https://x/2", "brand": "직방",
            "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀", "desc": "",
        }],
        market_news=[{
            "title": "시장뉴스", "url": "https://x/3", "brand": "AI",
            "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀", "desc": "",
        }],
    )
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "🏠 프롭티어 관련 뉴스 TOP3" in body_text
    assert "⚔️ 경쟁사 동향 TOP3" in body_text
    assert "🌐 시장 동향 TOP3" in body_text


def test_build_adaptive_card_renders_channel_counts_as_tiles():
    """가독성이 떨어진다는 피드백에 따라, 채널별 집계를 한 줄 텍스트가 아니라
    ColumnSet 안의 강조(emphasis) 타일로 렌더링한다."""
    content = _content(total_count=7, channel_counts={"네이버": 5, "구글": 2})
    payload = notify.build_adaptive_card(content, "2026-08-27")
    body = payload["attachments"][0]["content"]["body"]

    column_sets = [b for b in body if b.get("type") == "ColumnSet"]
    assert column_sets, "채널별 집계가 ColumnSet 타일로 렌더링되어야 한다"
    tile_containers = [
        col["items"][0] for cs in column_sets for col in cs["columns"]
    ]
    assert all(c["type"] == "Container" and c["style"] == "emphasis" for c in tile_containers)
    tile_texts = [t["text"] for c in tile_containers for t in c["items"]]
    assert "7" in tile_texts
    assert "네이버" in tile_texts
    assert "구글" in tile_texts


def test_build_adaptive_card_renders_news_items_as_styled_cards():
    """뉴스 항목도 얇은 구분선이 아니라 강조(emphasis) 박스로 렌더링해 눈에 잘 띄게 한다."""
    content = _content(total_count=1, own_brand_news=[{
        "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
        "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀", "desc": "요약",
    }])
    payload = notify.build_adaptive_card(content, "2026-08-27")
    body = payload["attachments"][0]["content"]["body"]

    item_cards = [b for b in body if b.get("type") == "Container" and b.get("style") == "emphasis"]
    assert item_cards, "뉴스 항목이 emphasis 스타일 카드로 렌더링되어야 한다"


def test_build_adaptive_card_includes_channel_counts_breakdown():
    content = _content(total_count=7, channel_counts={"네이버": 5, "구글": 2})
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "네이버" in body_text
    assert "구글" in body_text


def test_build_adaptive_card_includes_item_desc_and_posted_at():
    content = _content(
        total_count=1,
        own_brand_news=[{
            "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
            "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀", "desc": "요약 내용입니다",
        }],
    )
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "요약 내용입니다" in body_text
    assert "2026.08.27" in body_text


def test_build_adaptive_card_escapes_leading_markdown_heading_in_desc():
    """스크랩 원문이 문단 앞에 '#'을 쓰는 사이트(예: thescoop.co.kr)에서 온 경우, Adaptive
    Card 렌더러가 이를 헤딩으로 해석해 글자가 커지는 사고가 있었다 — 앞머리 '#'을
    이스케이프해 무력화해야 한다."""
    content = _content(total_count=1, own_brand_news=[{
        "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
        "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀",
        "desc": "# 문재인 정부가 집값 통계를 조작했다는 의혹",
    }])
    payload = notify.build_adaptive_card(content, "2026-08-27")
    body = payload["attachments"][0]["content"]["body"]

    item_card = next(b for b in body if b.get("type") == "Container" and b.get("style") == "emphasis")
    content_items = item_card["items"][0]["columns"][1]["items"]
    desc_block = next(t for t in content_items if t.get("isSubtle") and t.get("spacing") == "Small")
    assert desc_block["text"].startswith("\\#")


def test_build_adaptive_card_escapes_leading_markdown_heading_in_title():
    content = _content(total_count=1, own_brand_news=[{
        "title": "# 헤딩처럼 보이는 제목", "url": "https://x/1", "brand": "프롭티어",
        "channel": "네이버", "posted_at": "", "signal": "🚀", "desc": "",
    }])
    payload = notify.build_adaptive_card(content, "2026-08-27")
    body = payload["attachments"][0]["content"]["body"]

    item_card = next(b for b in body if b.get("type") == "Container" and b.get("style") == "emphasis")
    title_block = item_card["items"][0]["columns"][1]["items"][0]
    assert title_block["text"].startswith("[\\#")


def test_build_adaptive_card_leaves_normal_desc_text_unescaped():
    content = _content(total_count=1, own_brand_news=[{
        "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
        "channel": "네이버", "posted_at": "2026.08.27", "signal": "🚀",
        "desc": "평범한 요약 내용입니다",
    }])
    payload = notify.build_adaptive_card(content, "2026-08-27")
    body = payload["attachments"][0]["content"]["body"]

    item_card = next(b for b in body if b.get("type") == "Container" and b.get("style") == "emphasis")
    content_items = item_card["items"][0]["columns"][1]["items"]
    desc_block = next(t for t in content_items if t.get("isSubtle") and t.get("spacing") == "Small")
    assert desc_block["text"] == "평범한 요약 내용입니다"


def test_build_adaptive_card_limits_each_section_to_top_3():
    items = [
        {"title": f"뉴스{i}", "url": f"https://x/{i}", "brand": "프롭티어",
         "channel": "네이버", "posted_at": "", "signal": "🚀", "desc": ""}
        for i in range(4)
    ]
    content = _content(total_count=4, own_brand_news=items)
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "뉴스0" in body_text
    assert "뉴스1" in body_text
    assert "뉴스2" in body_text
    assert "뉴스3" not in body_text


def test_build_adaptive_card_omits_empty_sections():
    content = _content(
        total_count=1,
        own_brand_news=[{
            "title": "자사뉴스", "url": "https://x/1", "brand": "프롭티어",
            "channel": "네이버", "posted_at": "", "signal": "🚀", "desc": "",
        }],
        competitor_news=[],
    )
    payload = notify.build_adaptive_card(content, "2026-08-27")

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "경쟁사" not in body_text


def test_build_adaptive_card_more_button_links_to_local_when_deploy_host_present(monkeypatch):
    """DEPLOY_HOST가 있다는 것 자체가 이 프로세스가 로컬(관리자) 머신이라는 뜻이다 —
    배포된 서버 자신의 .env에는 DEPLOY_HOST가 없다(_filtered_env_content 참고)."""
    monkeypatch.setenv("DEPLOY_HOST", "192.168.10.169")
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.delenv("LOCAL_SITE_URL", raising=False)

    payload = notify.build_adaptive_card(_content(total_count=1), "2026-08-27")

    actions = payload["attachments"][0]["content"]["actions"]
    assert actions[0]["url"] == "http://localhost:8501/briefings"


def test_build_adaptive_card_more_button_links_to_site_url_when_deploy_host_absent(monkeypatch):
    monkeypatch.delenv("DEPLOY_HOST", raising=False)
    monkeypatch.setenv("SITE_URL", "http://192.168.10.169:7000")

    payload = notify.build_adaptive_card(_content(total_count=1), "2026-08-27")

    actions = payload["attachments"][0]["content"]["actions"]
    assert actions[0]["url"] == "http://192.168.10.169:7000/briefings"


def test_build_adaptive_card_omits_more_button_when_no_site_available(monkeypatch):
    monkeypatch.delenv("DEPLOY_HOST", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)

    payload = notify.build_adaptive_card(_content(total_count=1), "2026-08-27")

    assert "actions" not in payload["attachments"][0]["content"]


def test_build_test_card_wraps_as_teams_message():
    payload = notify.build_test_card()

    assert payload["type"] == "message"
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_build_test_card_includes_connection_test_text():
    payload = notify.build_test_card()

    body_text = str(payload["attachments"][0]["content"]["body"])
    assert "연결 테스트" in body_text


class _FakeResponse:
    def __init__(self, status_code=200, raise_error=None):
        self.status_code = status_code
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error


def test_send_webhook_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: _FakeResponse(200))

    ok, message = notify.send_webhook({"a": 1}, "https://example.com/hook")

    assert ok is True
    assert "200" in message


def test_send_webhook_retries_until_success(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(1)
        if len(calls) < 2:
            return _FakeResponse(500, raise_error=RuntimeError("server error"))
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    sleeps = []

    ok, _ = notify.send_webhook({"a": 1}, "https://example.com/hook", sleep_fn=sleeps.append)

    assert ok is True
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_send_webhook_returns_false_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(
        notify.requests, "post",
        lambda url, json, timeout: _FakeResponse(500, raise_error=RuntimeError("boom")),
    )

    ok, message = notify.send_webhook({"a": 1}, "https://example.com/hook", retries=2, sleep_fn=lambda s: None)

    assert ok is False
    assert "boom" in message


def test_send_webhook_does_not_sleep_when_retries_zero(monkeypatch):
    monkeypatch.setattr(
        notify.requests, "post",
        lambda url, json, timeout: _FakeResponse(500, raise_error=RuntimeError("boom")),
    )
    sleeps = []

    ok, _ = notify.send_webhook({"a": 1}, "https://example.com/hook", retries=0, sleep_fn=sleeps.append)

    assert ok is False
    assert sleeps == []


def test_send_test_webhook_sends_test_card_without_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(
        notify, "send_webhook",
        lambda payload, url, retries=3, sleep_fn=None: calls.append((payload, url, retries)) or (True, "ok"),
    )

    ok, message = notify.send_test_webhook("https://example.com/hook")

    assert ok is True
    payload, url, retries = calls[0]
    assert url == "https://example.com/hook"
    assert retries == 0
    assert payload == notify.build_test_card()


def test_build_daily_report_content_uses_todays_mentions_and_brand_sets(monkeypatch):
    from datetime import datetime

    fixed_now = datetime(2026, 8, 27, 9, 0, 0)
    monkeypatch.setattr(notify, "datetime", type("_D", (), {"now": staticmethod(lambda: fixed_now)}))

    captured = {}

    def fake_get_mentions(date_str):
        captured["date_str"] = date_str
        return ["mention1"]

    def fake_build_content(mentions, own, competitor, market, now=None):
        captured["mentions"] = mentions
        captured["own"] = own
        captured["competitor"] = competitor
        captured["market"] = market
        return _content(total_count=1)

    monkeypatch.setattr(notify.db, "get_mentions_by_collected_date", fake_get_mentions)
    monkeypatch.setattr(notify.news_feed, "own_brand_names", lambda: {"프롭티어"})
    monkeypatch.setattr(notify.news_feed, "competitor_brand_names", lambda: {"직방"})
    monkeypatch.setattr(notify.news_feed, "market_brand_names", lambda: {"AI"})
    monkeypatch.setattr(notify.news_feed, "build_briefing_archive_content", fake_build_content)

    report_date, content = notify.build_daily_report_content()

    assert report_date == "2026-08-27"
    assert captured["date_str"] == "2026-08-27"
    assert captured["mentions"] == ["mention1"]
    assert captured["own"] == {"프롭티어"}
    assert captured["competitor"] == {"직방"}
    assert captured["market"] == {"AI"}
    assert content["total_count"] == 1


def test_send_daily_report_logs_zero_targets_when_no_enabled_webhooks(monkeypatch):
    monkeypatch.setattr(notify, "build_daily_report_content", lambda: ("2026-08-27", _content()))
    monkeypatch.setattr(notify.utils, "load_webhooks", lambda: [])
    logged = []
    monkeypatch.setattr(notify.db, "insert_webhook_send_log", lambda entry: logged.append(entry))

    result = notify.send_daily_report(trigger="자동")

    assert result == {"targets": 0, "sent": 0}
    assert logged[0]["targets"] == 0
    assert logged[0]["sent"] == 0
    assert logged[0]["ok"] == 0
    assert logged[0]["trigger"] == "자동"


def test_send_daily_report_sends_only_to_enabled_webhooks_and_logs_summary(monkeypatch):
    monkeypatch.setattr(notify, "build_daily_report_content", lambda: ("2026-08-27", _content(total_count=5)))
    monkeypatch.setattr(notify.utils, "load_webhooks", lambda: [
        {"id": "a", "name": "A", "url": "https://x/a", "enabled": True},
        {"id": "b", "name": "B", "url": "https://x/b", "enabled": False},
        {"id": "c", "name": "C", "url": "https://x/c", "enabled": True},
    ])
    sent_urls = []
    monkeypatch.setattr(notify, "send_webhook", lambda payload, url: sent_urls.append(url) or (True, "ok"))
    logged = []
    monkeypatch.setattr(notify.db, "insert_webhook_send_log", lambda entry: logged.append(entry))

    result = notify.send_daily_report(trigger="수동")

    assert sent_urls == ["https://x/a", "https://x/c"]
    assert result == {"targets": 2, "sent": 2}
    assert logged[0]["targets"] == 2
    assert logged[0]["sent"] == 2
    assert logged[0]["ok"] == 1


def test_send_daily_report_marks_ok_false_on_partial_failure(monkeypatch):
    monkeypatch.setattr(notify, "build_daily_report_content", lambda: ("2026-08-27", _content(total_count=5)))
    monkeypatch.setattr(notify.utils, "load_webhooks", lambda: [
        {"id": "a", "name": "A", "url": "https://x/a", "enabled": True},
        {"id": "b", "name": "B", "url": "https://x/b", "enabled": True},
    ])
    monkeypatch.setattr(
        notify, "send_webhook",
        lambda payload, url: (True, "ok") if url.endswith("/a") else (False, "fail"),
    )
    logged = []
    monkeypatch.setattr(notify.db, "insert_webhook_send_log", lambda entry: logged.append(entry))

    result = notify.send_daily_report(trigger="수동")

    assert result == {"targets": 2, "sent": 1}
    assert logged[0]["ok"] == 0
