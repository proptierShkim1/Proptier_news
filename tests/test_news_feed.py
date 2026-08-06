from datetime import datetime

import news_feed


def _mention(title, brand="직방", url="https://x/1", collected_at="2026-08-05 09:00:00", snippet="", content=""):
    return {
        "title": title, "brand": brand, "url": url, "collected_at": collected_at,
        "snippet": snippet, "content": content, "channel": "네이버", "posted_at": "",
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


def test_build_news_items_truncates_long_content_to_preview_length():
    mentions = [_mention("직방 AI 매물 추천 출시", content="가" * 500)]

    items = news_feed.build_news_items(mentions, own_brands=set())

    desc = items[0]["desc"][0]
    assert desc.endswith("…")
    assert len(desc) == news_feed.CONTENT_PREVIEW_LEN + 1


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
