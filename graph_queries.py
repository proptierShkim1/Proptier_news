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


def policy_event_mention_impact(
    policy_keyword: str, before_days: int = 7, after_days: int = 7
) -> dict:
    """제목에 policy_keyword가 포함된 정책 발표를 찾아, 그 발표일 전/후 기간의 관련
    뉴스 언급 건수를 비교한다 — "이 정책 발표 전후로 관련 브랜드 뉴스가 늘었어?" 같은
    질문에 쓴다. 최근 365일 내에서 가장 최근에 매칭되는 발표 하나를 기준으로 삼는다.

    Args:
        policy_keyword: 정책 발표 제목에서 찾을 키워드(예: "전세사기 특별법").
        before_days: 발표일 이전 며칠을 "전" 기간으로 볼지 (기본 7일).
        after_days: 발표일 이후 며칠을 "후" 기간으로 볼지 (기본 7일).

    Returns:
        매칭되는 발표가 없으면 {"found": False, "policy_keyword": str}. 있으면
        {"found": True, "policy_event": {"title": str, "announced_at": str},
        "before_count": int, "after_count": int, "change": int} — change는
        after_count - before_count. 발표의 카테고리와 대응되는 뉴스카테고리가 온톨로지에
        없으면 카테고리로 거르지 않고 기간 내 전체 언급을 집계한다.
    """
    events = cached_db.get_policy_events_since(365)
    matches = [e for e in events if policy_keyword in e.get("title", "")]
    if not matches:
        return {"found": False, "policy_keyword": policy_keyword}

    event = max(matches, key=lambda e: e.get("announced_at") or "")
    announced_str = (event.get("announced_at") or "")[:10]
    if not announced_str:
        return {"found": False, "policy_keyword": policy_keyword}
    announced_date = datetime.strptime(announced_str, "%Y-%m-%d").date()

    related_news_categories: set[str] = set()
    for category in policy_feed.categorize(event.get("title", "")):
        related_news_categories.update(ontology.aligned_news_categories(category))

    fetch_days = (_today() - announced_date).days + before_days + 1
    mentions = cached_db.get_mentions_since(fetch_days)

    before_start = (announced_date - timedelta(days=before_days)).isoformat()
    announced_iso = announced_date.isoformat()
    after_end = (announced_date + timedelta(days=after_days)).isoformat()

    before_count = 0
    after_count = 0
    for m in mentions:
        m_date = (m.get("collected_at") or "")[:10]
        if not m_date:
            continue
        if related_news_categories:
            text = f"{m.get('title', '')} {m.get('snippet', '')}"
            if not related_news_categories & set(news_feed.categorize(text)):
                continue
        if before_start <= m_date < announced_iso:
            before_count += 1
        elif announced_iso <= m_date <= after_end:
            after_count += 1

    return {
        "found": True,
        "policy_event": {"title": event.get("title", ""), "announced_at": announced_str},
        "before_count": before_count,
        "after_count": after_count,
        "change": after_count - before_count,
    }


def brand_role_category_breakdown(days: int = 30) -> dict:
    """최근 N일간 언급을 브랜드 role(own/competitor/market, keywords.json 기준) ×
    뉴스카테고리로 교차집계한다 — "경쟁사들이 어느 카테고리에서 우리보다 많이
    언급돼?" 같은 질문에 쓴다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        role을 키로, {카테고리명: 건수} 딕셔너리를 값으로 갖는 딕셔너리. 한 기사가
        여러 카테고리에 동시에 해당할 수 있어 role별 합계가 전체 언급 건수보다 클 수
        있다. keywords.json에 등록되지 않은 브랜드의 언급은 집계에서 제외된다.
    """
    brands = utils.load_keywords().get("brands", [])
    role_by_brand = {b["name"]: b.get("role", "market") for b in brands}
    mentions = cached_db.get_mentions_since(days)
    result: dict[str, dict[str, int]] = {}
    for m in mentions:
        role = role_by_brand.get(m.get("brand", ""))
        if not role:
            continue
        text = f"{m.get('title', '')} {m.get('snippet', '')}"
        bucket = result.setdefault(role, {})
        for category in news_feed.categorize(text):
            bucket[category] = bucket.get(category, 0) + 1
    return result
