from datetime import datetime

import news_feed


def _mention(title, brand="직방", url="https://x/1", collected_at="2026-08-05 09:00:00", snippet="",
              content="", summary="", mention_id=1):
    return {
        "id": mention_id, "title": title, "brand": brand, "url": url, "collected_at": collected_at,
        "snippet": snippet, "content": content, "summary": summary, "channel": "네이버", "posted_at": "",
    }


def test_build_news_items_uses_real_snippet_as_desc_when_it_differs_from_title():
    mentions = [_mention("직방 AI 매물 추천 출시", snippet="허위매물을 자동으로 걸러내는 기능이 핵심이다")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["desc"] == ["허위매물을 자동으로 걸러내는 기능이 핵심이다"]


def test_build_news_items_falls_back_to_channel_note_when_snippet_missing_or_duplicates_title():
    mentions = [_mention("직방 AI 매물 추천 출시", snippet="")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert "네이버" in items[0]["desc"][0]
    assert items[0]["desc"][0] != "직방 AI 매물 추천 출시"


def test_build_news_items_prefers_full_content_over_snippet_when_available():
    mentions = [_mention(
        "직방 AI 매물 추천 출시", snippet="짧은 미리보기",
        content="원문 첫 문단입니다. " * 5,
    )]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["desc"][0].startswith("원문 첫 문단입니다.")
    assert "짧은 미리보기" not in items[0]["desc"][0]


def test_build_news_items_desc_long_uses_ai_summary_when_present():
    mentions = [_mention(
        "직방 AI 매물 추천 출시", content="원문입니다. " * 50, summary="AI가 생성한 짧은 요약입니다.",
    )]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["desc_long"] == ["AI가 생성한 짧은 요약입니다."]


def test_build_news_items_desc_long_falls_back_to_truncated_content_without_summary():
    mentions = [_mention("직방 AI 매물 추천 출시", content="원문입니다. " * 50, summary="")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["desc_long"][0] != items[0]["desc"][0] or len(items[0]["desc_long"][0]) >= len(items[0]["desc"][0])
    assert items[0]["desc_long"][0].startswith("원문입니다.")


def test_build_news_items_exposes_mention_id_content_and_summary_for_pdf_backfill():
    mentions = [_mention("제목", content="원문", summary="요약", mention_id=42)]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["mention_id"] == 42
    assert items[0]["content"] == "원문"
    assert items[0]["summary"] == "요약"


def test_build_news_items_truncates_long_content_to_preview_length():
    mentions = [_mention("직방 AI 매물 추천 출시", content="가" * (news_feed.CONTENT_PREVIEW_LEN + 100))]

    items = news_feed.build_news_items(mentions, own_brands=set())

    desc = items[0]["desc"][0]
    assert desc.endswith("…")
    assert len(desc) == news_feed.CONTENT_PREVIEW_LEN + 1


def test_build_news_items_flags_has_real_content_false_when_falling_back_to_channel_note():
    mentions = [_mention("직방 AI 매물 추천 출시", snippet="")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["has_real_content"] is False


def test_build_news_items_flags_has_real_content_true_when_snippet_differs_from_title():
    mentions = [_mention("직방 AI 매물 추천 출시", snippet="허위매물을 자동으로 걸러내는 기능이 핵심이다")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["has_real_content"] is True


def test_build_news_items_flags_has_real_content_true_when_content_present():
    mentions = [_mention("직방 AI 매물 추천 출시", content="원문 첫 문단입니다.")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["has_real_content"] is True


def test_build_news_items_decision_line_names_matched_categories():
    mentions = [_mention("직방 AI 매물 추천 서비스 출시")]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert "AI" in items[0]["decision"][0]


def test_build_issues_clusters_similar_titles_from_same_brand_within_window():
    mentions = [
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-05 09:00:00"),
        _mention("직방 AI 매물 추천 서비스 정식 출시…허위매물 자동 필터링", collected_at="2026-08-05 11:00:00"),
    ]

    issues = news_feed.build_issues(mentions)

    assert len(issues) == 1
    assert issues[0]["count"] == 2
    assert len(issues[0]["articles"]) == 2


def test_build_issues_does_not_cluster_dissimilar_titles():
    mentions = [
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-05 09:00:00"),
        _mention("직방, 3분기 매출 32% 증가 발표", collected_at="2026-08-05 09:30:00"),
    ]

    issues = news_feed.build_issues(mentions)

    assert len(issues) == 2
    assert all(i["count"] == 1 for i in issues)


def test_build_issues_does_not_cluster_across_different_brands():
    mentions = [
        _mention("AI 매물 추천 서비스 정식 출시", brand="직방", collected_at="2026-08-05 09:00:00"),
        _mention("AI 매물 추천 서비스 정식 출시", brand="다방", collected_at="2026-08-05 09:00:00"),
    ]

    issues = news_feed.build_issues(mentions)

    assert len(issues) == 2
    assert {i["firm"] for i in issues} == {"직방", "다방"}


def test_build_issues_does_not_cluster_similar_titles_outside_time_window():
    mentions = [
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-01 09:00:00"),
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-10 09:00:00"),
    ]

    issues = news_feed.build_issues(mentions)

    assert len(issues) == 2


def test_build_issues_representative_title_is_earliest_mention():
    mentions = [
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-05 09:00:00"),
        _mention("직방 AI 매물 추천 서비스 정식 출시 - 후속 보도", collected_at="2026-08-05 15:00:00"),
    ]

    issues = news_feed.build_issues(mentions)

    assert len(issues) == 1
    assert issues[0]["title"] == "직방, AI 매물 추천 서비스 정식 출시"


def test_build_issues_live_true_if_any_article_recent():
    # 두 기사 간 간격(34시간)은 CLUSTER_WINDOW_HOURS(48) 이내라 같은 이슈로 묶이고,
    # now 기준으로는 최신 기사만 RECENCY_HOURS(12) 이내라 이슈 전체가 live로 표시돼야 함
    now = datetime(2026, 8, 5, 20, 0, 0)
    mentions = [
        _mention("직방, AI 매물 추천 서비스 정식 출시", collected_at="2026-08-04 09:00:00"),
        _mention("직방 AI 매물 추천 서비스 정식 출시 후속", collected_at="2026-08-05 19:00:00"),
    ]

    issues = news_feed.build_issues(mentions, now=now)

    assert len(issues) == 1
    assert issues[0]["live"] is True


def test_competitor_brand_names_returns_only_competitor_role(monkeypatch):
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": [
        {"name": "프롭티어", "role": "own"},
        {"name": "직방", "role": "competitor"},
        {"name": "AI", "role": "market"},
    ]})

    assert news_feed.competitor_brand_names() == {"직방"}


def test_market_brand_names_returns_only_market_role(monkeypatch):
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": [
        {"name": "프롭티어", "role": "own"},
        {"name": "직방", "role": "competitor"},
        {"name": "AI", "role": "market"},
    ]})

    assert news_feed.market_brand_names() == {"AI"}


def _mention_full(title, brand, channel, collected_at, mention_id):
    return {
        "id": mention_id, "title": title, "brand": brand, "url": f"https://x/{mention_id}",
        "collected_at": collected_at, "snippet": "", "content": "", "summary": "",
        "channel": channel, "posted_at": "2026.08.10",
    }


def test_build_news_items_includes_channel_and_posted_at_fields():
    mentions = [_mention_full("제목", "직방", "네이버뉴스API", "2026-08-10 09:00:00", 1)]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["channel"] == "네이버뉴스API"
    assert items[0]["posted_at"] == "2026.08.10"


def test_build_briefing_archive_content_splits_by_brand_role():
    mentions = [
        _mention_full("프롭티어 신규 서비스", "프롭티어", "네이버", "2026-08-10 09:00:00", 1),
        _mention_full("직방 매물 공개", "직방", "구글", "2026-08-10 10:00:00", 2),
        _mention_full("AI 시장 동향", "AI", "매경API", "2026-08-10 11:00:00", 3),
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands={"프롭티어"}, competitor_brands={"직방"}, market_brands={"AI"},
    )

    assert result["own_brand_news"][0]["title"] == "프롭티어 신규 서비스"
    assert result["competitor_news"][0]["title"] == "직방 매물 공개"
    assert result["market_news"][0]["title"] == "AI 시장 동향"
    assert result["total_count"] == 3


def test_build_briefing_archive_content_channel_counts_and_top_news():
    mentions = [
        _mention_full("기사1", "직방", "네이버", "2026-08-10 09:00:00", 1),
        _mention_full("기사2", "다방", "네이버", "2026-08-10 10:00:00", 2),
        _mention_full("기사3", "직방", "구글", "2026-08-10 11:00:00", 3),
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands=set(), competitor_brands={"직방", "다방"}, market_brands=set(),
    )

    assert result["channel_counts"] == {"네이버": 2, "구글": 1}
    assert len(result["channel_top_news"]["네이버"]) == 2
    assert len(result["channel_top_news"]["구글"]) == 1


def test_build_briefing_archive_content_limits_each_section_to_top_n():
    mentions = [
        _mention_full(f"직방 기사{i}", "직방", "네이버", f"2026-08-10 0{i}:00:00", i)
        for i in range(1, 8)
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands=set(), competitor_brands={"직방"}, market_brands=set(),
    )

    assert len(result["competitor_news"]) == 5
    assert len(result["channel_top_news"]["네이버"]) == 3
