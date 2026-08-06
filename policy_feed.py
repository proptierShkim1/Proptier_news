"""
hana_p — policy_events 원본 데이터를 "정책 뉴스" 화면 표시 형태로 가공.
news_feed.py와 같은 패턴(키워드 기반 카테고리·점수·메달 휴리스틱)을 정책 데이터에 적용한다.
"""

from datetime import datetime, timedelta
from functools import lru_cache

RECENCY_DAYS = 3
DISPLAY_LIMIT = 30

POLICY_CATEGORY_KEYWORDS = {
    "규제·법령": ["규제", "법령", "시행령", "개정", "고시", "제정"],
    "지원·사업": ["지원", "사업", "공급", "보조금", "융자", "추진"],
    "통계·조사": ["통계", "조사", "실태", "지수", "동향"],
    "조직·인사": ["인사", "조직", "임명", "위촉", "발령"],
    "행사·홍보": ["행사", "홍보", "박람회", "설명회", "협약"],
}
POLICY_CATEGORY_ORDER = list(POLICY_CATEGORY_KEYWORDS.keys())
POLICY_CATEGORY_EMOJI = {
    "규제·법령": "⚖️", "지원·사업": "🏗️", "통계·조사": "📊", "조직·인사": "🧑‍💼", "행사·홍보": "📣",
}
FALLBACK_CATEGORY = "일반"
FALLBACK_EMOJI = "📰"


@lru_cache(maxsize=4096)
def categorize(title: str) -> list[str]:
    """build_policy_items/build_policy_pulse가 같은 title로 각자 categorize()를 다시
    호출하는 중복을 캐싱으로 줄인다."""
    matched = [name for name, kws in POLICY_CATEGORY_KEYWORDS.items() if any(k in title for k in kws)]
    return matched or [FALLBACK_CATEGORY]


def _signal_label(categories: list[str]) -> str:
    for name in POLICY_CATEGORY_ORDER:
        if name in categories:
            return f"{POLICY_CATEGORY_EMOJI[name]} {name}"
    return f"{FALLBACK_EMOJI} {FALLBACK_CATEGORY}"


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _is_recent(event: dict, now: datetime) -> bool:
    d = _parse_date(event.get("announced_at", ""))
    return bool(d and (now.date() - d.date()).days <= RECENCY_DAYS)


def _score(event: dict, categories: list[str], now: datetime) -> int:
    score = 2 * len([c for c in categories if c != FALLBACK_CATEGORY])
    if _is_recent(event, now):
        score += 3
    if (event.get("view_count") or 0) >= 500:
        score += 2
    return score


def build_policy_items(events: list[dict], now: datetime | None = None) -> list[dict]:
    """policy_events 원본을 정책 시그널 카드 형태로 변환하고 점수 내림차순으로 정렬한다."""
    now = now or datetime.now()
    items = []
    for e in events:
        categories = categorize(e.get("title", ""))
        items.append({
            "score": _score(e, categories, now),
            "title": e.get("title", ""),
            "url": e.get("url", ""),
            "source": e.get("source", ""),
            "department": e.get("department") or "-",
            "view_count": e.get("view_count", 0),
            "announced_at": e.get("announced_at", ""),
            "categories": categories,
            "signal": _signal_label(categories),
        })
    items.sort(key=lambda it: (it["score"], it["announced_at"]), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    for i, it in enumerate(items):
        it["medal"] = medals[i] if i < 3 else str(i + 1)
    return items


def build_daily(events: list[dict], now: datetime | None = None, window_days: int = 14) -> list[tuple]:
    """now 기준 최근 window_days일을 하루 단위로 나눠 발표 건수를 센다 (과거→현재 순)."""
    now = now or datetime.now()
    counts = {}
    for e in events:
        d = _parse_date(e.get("announced_at", ""))
        if d:
            key = d.strftime("%Y-%m-%d")
            counts[key] = counts.get(key, 0) + 1
    buckets = []
    for i in range(window_days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        key = day.strftime("%Y-%m-%d")
        buckets.append((f"{day.month}/{day.day}", counts.get(key, 0)))
    return buckets


def build_policy_pulse(events: list[dict]) -> tuple:
    """카테고리(일반 제외) 중 가장 많이 매칭된 것과 건수를 반환."""
    counts = {}
    for e in events:
        for c in categorize(e.get("title", "")):
            if c != FALLBACK_CATEGORY:
                counts[c] = counts.get(c, 0) + 1
    if not counts:
        return ("-", 0)
    return max(counts.items(), key=lambda kv: kv[1])


def build_source_pulse(events: list[dict]) -> tuple:
    """가장 많이 발표한 기관과 건수를 반환."""
    counts = {}
    for e in events:
        counts[e["source"]] = counts.get(e["source"], 0) + 1
    if not counts:
        return ("-", 0)
    return max(counts.items(), key=lambda kv: kv[1])


def category_legend_markdown() -> str:
    """POLICY_CATEGORY_KEYWORDS를 기준으로 '?' 팝업에 쓸 카테고리 설명을 자동 생성."""
    lines = ["제목에 포함된 키워드로 정책 유형을 자동 분류합니다.\n"]
    for name in POLICY_CATEGORY_ORDER:
        emoji = POLICY_CATEGORY_EMOJI[name]
        keywords = ", ".join(POLICY_CATEGORY_KEYWORDS[name])
        lines.append(f"- **{emoji} {name}** — {keywords}")
    lines.append(f"- **{FALLBACK_EMOJI} {FALLBACK_CATEGORY}** — 위 키워드가 없는 보도자료")
    return "\n".join(lines)
