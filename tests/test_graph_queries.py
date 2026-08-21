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
