from datetime import date

import graph_queries


def test_category_alignment_counts_for_news_category(monkeypatch):
    mentions = [
        {"title": "국토부 정책 발표", "snippet": ""},
        {"title": "전세 매물 급증", "snippet": ""},
    ]
    events = [
        {"title": "전월세 신고제 시행령 개정"},
        {"title": "임대주택 지원 사업 확대"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)

    result = graph_queries.category_alignment_counts(news_category="정책", days=30)

    assert result == {
        "news_category": "정책",
        "aligned_policy_categories": ["규제·법령", "지원·사업"],
        "news_count": 1,
        "policy_counts": {"규제·법령": 1, "지원·사업": 1},
        "days": 30,
    }


def test_category_alignment_counts_for_policy_category(monkeypatch):
    mentions = [
        {"title": "전세 매물 급증", "snippet": ""},
        {"title": "국토부 정책 발표", "snippet": ""},
    ]
    events = [{"title": "임대주택 지원 사업 확대"}]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)

    result = graph_queries.category_alignment_counts(policy_category="지원·사업", days=30)

    assert result == {
        "policy_category": "지원·사업",
        "aligned_news_categories": ["정책", "매물"],
        "policy_count": 1,
        "news_counts": {"정책": 1, "매물": 1},
        "days": 30,
    }


def test_category_alignment_counts_returns_all_pairs_when_no_filter(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(days=30)

    assert [pair["news_category"] for pair in result] == ["정책", "매물", "시세·감정"]


def test_category_alignment_counts_unknown_news_category_returns_empty_alignment(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(news_category="해외", days=30)

    assert result["aligned_policy_categories"] == []
    assert result["policy_counts"] == {}


def test_category_alignment_counts_prefers_news_category_when_both_given(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(
        news_category="정책", policy_category="지원·사업", days=30
    )

    assert result["news_category"] == "정책"


def test_policy_event_mention_impact_not_found(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.policy_event_mention_impact("전세사기")

    assert result == {"found": False, "policy_keyword": "전세사기"}


def test_policy_event_mention_impact_found_counts_before_after(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"}]
    mentions = [
        {"title": "국토부 정책 발표", "snippet": "", "collected_at": "2026-08-05"},
        {"title": "정책 대책 발표", "snippet": "", "collected_at": "2026-08-12"},
        {"title": "정책 제도 개편", "snippet": "", "collected_at": "2026-08-14"},
        {"title": "전세 매물 정보", "snippet": "", "collected_at": "2026-08-11"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(
        graph_queries.cached_db,
        "get_mentions_between",
        lambda start_days_ago, end_days_ago: mentions,
    )

    result = graph_queries.policy_event_mention_impact("전세사기", before_days=7, after_days=7)

    assert result == {
        "found": True,
        "policy_event": {"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"},
        "before_count": 1,
        "after_count": 2,
        "change": 1,
        "related_news_categories": ["정책"],
    }


def test_policy_event_mention_impact_no_alignment_counts_all_mentions(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "국토부 인사 발령", "announced_at": "2026-08-15"}]
    mentions = [
        {"title": "전세 매물 정보", "snippet": "", "collected_at": "2026-08-12"},
        {"title": "미국 부동산 동향", "snippet": "", "collected_at": "2026-08-16"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(
        graph_queries.cached_db,
        "get_mentions_between",
        lambda start_days_ago, end_days_ago: mentions,
    )

    result = graph_queries.policy_event_mention_impact("인사", before_days=7, after_days=7)

    assert result["before_count"] == 1
    assert result["after_count"] == 1


def test_policy_event_mention_impact_asymmetric_window_fetches_enough_history(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "국토부 인사 발령", "announced_at": "2026-08-16"}]
    mentions = [{"title": "전세 매물 정보", "snippet": "", "collected_at": "2026-07-18"}]
    seen_windows = []

    def fake_get_mentions_between(start_days_ago, end_days_ago):
        seen_windows.append((start_days_ago, end_days_ago))
        return mentions

    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_between", fake_get_mentions_between)

    result = graph_queries.policy_event_mention_impact("인사", before_days=30, after_days=1)

    assert seen_windows[0][0] >= 35  # start_days_ago must reach back to before_start (2026-07-17)
    assert result["before_count"] == 1


def test_policy_event_mention_impact_after_window_excludes_day_after_after_days(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"}]
    mentions = [
        {"title": "정책 대책 발표", "snippet": "", "collected_at": "2026-08-17"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_between", lambda s, e: mentions)

    result = graph_queries.policy_event_mention_impact("전세사기", before_days=7, after_days=7)

    assert result["after_count"] == 0


def test_policy_event_mention_impact_includes_related_news_categories(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"}]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_between", lambda s, e: [])

    result = graph_queries.policy_event_mention_impact("전세사기")

    assert result["related_news_categories"] == ["정책"]


def test_policy_event_mention_impact_related_news_categories_empty_when_no_alignment(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "국토부 인사 발령", "announced_at": "2026-08-15"}]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_between", lambda s, e: [])

    result = graph_queries.policy_event_mention_impact("인사")

    assert result["related_news_categories"] == []


def test_policy_event_mention_impact_start_days_ago_has_one_day_margin(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "국토부 인사 발령", "announced_at": "2026-08-15"}]
    seen_windows = []

    def fake_get_mentions_between(start_days_ago, end_days_ago):
        seen_windows.append((start_days_ago, end_days_ago))
        return []

    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_between", fake_get_mentions_between)

    graph_queries.policy_event_mention_impact("인사", before_days=7, after_days=7)

    # before_start_date = 2026-08-08; (today - before_start_date).days = 13 exactly.
    # start_days_ago must be 14 (13 + the 1-day safety margin) — without the margin this
    # would be 13, and the assertion would fail, proving the margin is actually present.
    assert seen_windows[0][0] == 14


def test_brand_role_category_breakdown(monkeypatch):
    monkeypatch.setattr(
        graph_queries.utils,
        "load_keywords",
        lambda: {
            "brands": [
                {"name": "프롭티어", "role": "own"},
                {"name": "직방", "role": "competitor"},
            ]
        },
    )
    mentions = [
        {"brand": "프롭티어", "title": "프롭티어 AI 신규 도입", "snippet": ""},
        {"brand": "직방", "title": "직방 전세 매물 확대", "snippet": ""},
        {"brand": "알수없는브랜드", "title": "매물 정보", "snippet": ""},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)

    result = graph_queries.brand_role_category_breakdown(days=30)

    assert result == {
        "own": {"신규 도입": 1, "AI": 1, "부동산AI": 1},
        "competitor": {"매물": 1},
    }
