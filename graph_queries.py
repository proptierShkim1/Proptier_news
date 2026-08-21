"""
hana_p — ontology.py의 정적 관계와 cached_db/categorize()를 조합해, mentions와
policy_events를 카테고리·날짜 기준으로 엮는 조회 함수(그래프형 쿼리)를 제공한다.
SQL JOIN이나 스키마 변경 없이 Python 레벨에서 조인한다 — 자세한 배경은
docs/superpowers/specs/2026-08-21-ontology-graph-queries-design.md 참고.
"""

from datetime import date, datetime, timedelta

import cached_db
import news_feed
import ontology
import policy_feed
import utils


def _today() -> date:
    return date.today()


def _mention_count_for_category(mentions: list[dict], category: str) -> int:
    return sum(
        1
        for m in mentions
        if category in news_feed.categorize(f"{m.get('title', '')} {m.get('snippet', '')}")
    )


def _policy_count_for_category(events: list[dict], category: str) -> int:
    return sum(1 for e in events if category in policy_feed.categorize(e.get("title", "")))


def _news_category_alignment(news_category: str, days: int) -> dict:
    aligned = ontology.aligned_policy_categories(news_category)
    mentions = cached_db.get_mentions_since(days)
    events = cached_db.get_policy_events_since(days)
    return {
        "news_category": news_category,
        "aligned_policy_categories": aligned,
        "news_count": _mention_count_for_category(mentions, news_category),
        "policy_counts": {pc: _policy_count_for_category(events, pc) for pc in aligned},
        "days": days,
    }


def _policy_category_alignment(policy_category: str, days: int) -> dict:
    aligned = ontology.aligned_news_categories(policy_category)
    mentions = cached_db.get_mentions_since(days)
    events = cached_db.get_policy_events_since(days)
    return {
        "policy_category": policy_category,
        "aligned_news_categories": aligned,
        "policy_count": _policy_count_for_category(events, policy_category),
        "news_counts": {nc: _mention_count_for_category(mentions, nc) for nc in aligned},
        "days": days,
    }


def category_alignment_counts(
    news_category: str = "", policy_category: str = "", days: int = 30
) -> dict | list[dict]:
    """뉴스카테고리와 정책카테고리 중 서로 대응되는(온톨로지로 정렬된) 카테고리가 최근
    며칠간 각각 몇 건씩 나왔는지 알려준다 — "정책 카테고리별로 요즘 어떤 뉴스카테고리가
    같이 뜨고 있어?" 같은, 두 분류 체계를 엮는 질문에 쓴다.

    Args:
        news_category: 조회할 뉴스카테고리(신규 도입/AI/부동산AI/매물/시세·감정/정책/
            해외/리포트 중 하나). 지정하면 대응되는 정책카테고리들의 건수를 함께 반환.
        policy_category: 조회할 정책카테고리(규제·법령/지원·사업/통계·조사/조직·인사/
            행사·홍보 중 하나). news_category가 없을 때만 쓰이며, 지정하면 대응되는
            뉴스카테고리들의 건수를 함께 반환.
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        news_category를 줬으면 {"news_category": str, "aligned_policy_categories":
        list[str], "news_count": int, "policy_counts": {정책카테고리: int, ...},
        "days": int}. policy_category만 줬으면 {"policy_category": str,
        "aligned_news_categories": list[str], "policy_count": int, "news_counts":
        {뉴스카테고리: int, ...}, "days": int}. 둘 다 안 주면 온톨로지에 선언된 모든
        뉴스카테고리 각각에 대해 위 news_category 형태의 딕셔너리를 담은 리스트.
        대응되는 카테고리가 없으면 aligned_* 리스트가 빈 채로 정상 반환된다.
    """
    if news_category:
        return _news_category_alignment(news_category, days)
    if policy_category:
        return _policy_category_alignment(policy_category, days)
    return [_news_category_alignment(nc, days) for nc in ontology.CATEGORY_ALIGNMENT]
