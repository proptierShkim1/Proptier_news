from datetime import datetime

import policy_feed


def _event(title, source="국토교통부", department="주택정책과", view_count=100,
           announced_at="2026-08-05", url="https://x/1"):
    return {
        "title": title, "source": source, "department": department,
        "view_count": view_count, "announced_at": announced_at, "url": url,
    }


def test_categorize_matches_keyword_to_category():
    assert policy_feed.categorize("전세사기 방지 법령 개정안 시행") == ["규제·법령"]


def test_categorize_falls_back_when_no_keyword_matches():
    assert policy_feed.categorize("아무 상관없는 제목") == [policy_feed.FALLBACK_CATEGORY]


def test_build_policy_items_sorts_by_score_descending():
    now = datetime(2026, 8, 5, 12, 0, 0)
    events = [
        _event("아무 상관없는 제목", view_count=10, announced_at="2026-07-01", url="https://x/1"),
        _event("전세사기 방지 법령 개정안 시행", view_count=800, announced_at="2026-08-05", url="https://x/2"),
    ]

    items = policy_feed.build_policy_items(events, now)

    assert items[0]["url"] == "https://x/2"
    assert items[0]["score"] > items[1]["score"]


def test_build_policy_items_assigns_medals_to_top_three():
    now = datetime(2026, 8, 5, 12, 0, 0)
    events = [_event(f"제목{i}", url=f"https://x/{i}") for i in range(4)]

    items = policy_feed.build_policy_items(events, now)

    assert [it["medal"] for it in items[:3]] == ["\U0001F947", "\U0001F948", "\U0001F949"]
    assert items[3]["medal"] == "4"


def test_build_daily_buckets_counts_by_announced_date_within_window():
    now = datetime(2026, 8, 5, 12, 0, 0)
    events = [
        _event("제목1", announced_at="2026-08-05", url="https://x/1"),
        _event("제목2", announced_at="2026-08-05", url="https://x/2"),
        _event("제목3", announced_at="2026-08-04", url="https://x/3"),
    ]

    daily = policy_feed.build_daily(events, now, window_days=3)

    assert daily[-1] == ("8/5", 2)
    assert daily[-2] == ("8/4", 1)
    assert daily[-3] == ("8/3", 0)


def test_build_policy_pulse_returns_most_frequent_non_fallback_category():
    events = [
        _event("전세사기 방지 법령 개정안", url="https://x/1"),
        _event("임대차 시행령 개정 추진", url="https://x/2"),
        _event("아무 상관없는 제목", url="https://x/3"),
    ]

    category, count = policy_feed.build_policy_pulse(events)

    assert category == "규제·법령"
    assert count == 2


def test_build_source_pulse_returns_most_frequent_source():
    events = [
        _event("제목1", source="국토교통부", url="https://x/1"),
        _event("제목2", source="LH", url="https://x/2"),
        _event("제목3", source="LH", url="https://x/3"),
    ]

    source, count = policy_feed.build_source_pulse(events)

    assert source == "LH"
    assert count == 2
