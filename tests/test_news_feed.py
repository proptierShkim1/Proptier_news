from datetime import datetime

import news_feed


def _mention(title, brand="직방", url="https://x/1", collected_at="2026-08-05 09:00:00", snippet=""):
    return {
        "title": title, "brand": brand, "url": url, "collected_at": collected_at,
        "snippet": snippet, "channel": "네이버", "posted_at": "",
    }


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
