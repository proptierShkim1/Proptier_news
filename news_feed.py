"""
hana_p — mentions 원본 데이터를 "오늘의 뉴스" 화면 표시 형태로 가공.
카테고리 분류·점수·메달은 실제 수집 데이터에 없는 필드라 키워드 기반 휴리스틱으로 계산한다.
"""

from datetime import datetime, timedelta

from utils import load_channel_visibility, load_keywords

RECENT_LIMIT = 200
BROAD_LIMIT = 1000
DISPLAY_LIMIT = 30
RECENCY_HOURS = 12

CATEGORY_KEYWORDS = {
    "신규 도입": ["출시", "도입", "런칭", "오픈", "신규", "베타", "공개"],
    "AI": ["AI", "인공지능", "챗봇", "생성형", "LLM", "머신러닝", "딥러닝"],
    "부동산AI": ["부동산AI", "프롭테크", "프롭티어"],
    "매물": ["매물", "급매", "전세", "월세", "매매", "임대", "분양"],
    "시세·감정": ["시세", "감정가", "실거래가", "호가", "감정평가"],
    "정책": ["정책", "규제", "국토부", "국토교통부", "법안", "대책", "제도"],
    "해외": ["해외", "글로벌", "미국", "중국", "일본", "유럽"],
    "리포트": ["보고서", "리포트", "백서", "연구"],
}
CATEGORY_ORDER = list(CATEGORY_KEYWORDS.keys())
CATEGORY_EMOJI = {
    "신규 도입": "🚀", "AI": "🤖", "부동산AI": "🏠", "매물": "🏢",
    "시세·감정": "📊", "정책": "🏛️", "해외": "🌍", "리포트": "📄",
}
FALLBACK_CATEGORY = "일반"
FALLBACK_EMOJI = "📰"
CATEGORY_COLORS = {
    "신규 도입": ("#fff1e0", "#c2660c"),
    "AI": ("#e7f0ff", "#1d4ed8"),
    "부동산AI": ("#e7f0ff", "#1d4ed8"),
    "매물": ("#fef6da", "#9a6a07"),
    "시세·감정": ("#fef6da", "#9a6a07"),
    "정책": ("#e7f0ff", "#1d4ed8"),
    "해외": ("#eef2f3", "#4d5f66"),
    "리포트": ("#fef6da", "#9a6a07"),
    FALLBACK_CATEGORY: ("#eef2f3", "#4d5f66"),
}


def category_legend_markdown() -> str:
    """카테고리 배지/탭이 어떻게 나뉘는지 설명하는 도움말 텍스트. 키워드 사전이 바뀌면
    이 텍스트도 자동으로 최신 상태를 반영한다(하드코딩된 설명이 따로 없음)."""
    lines = [
        "카테고리는 제목·요약에 포함된 키워드를 기준으로 **자동 분류**됩니다 "
        "(사람이 직접 분류한 것이 아닙니다).",
        "",
    ]
    for name in CATEGORY_ORDER:
        keywords = ", ".join(CATEGORY_KEYWORDS[name])
        lines.append(f"- {CATEGORY_EMOJI[name]} **{name}** — 포함 키워드: {keywords}")
    lines.append(f"- {FALLBACK_EMOJI} **{FALLBACK_CATEGORY}** — 위 8개 중 하나도 해당하지 않는 경우")
    lines.append("")
    lines.append("한 기사가 여러 카테고리에 동시에 해당할 수 있습니다.")
    return "\n".join(lines)


def enabled_channels() -> list:
    return load_channel_visibility()


def own_brand_names() -> set:
    return {b["name"] for b in load_keywords().get("brands", []) if b.get("role") == "own"}


def all_brand_names() -> list[str]:
    return [b["name"] for b in load_keywords().get("brands", [])]


def categorize(text: str) -> list[str]:
    matched = [name for name, kws in CATEGORY_KEYWORDS.items() if any(k in text for k in kws)]
    return matched or [FALLBACK_CATEGORY]


def _signal_label(categories: list[str]) -> str:
    for name in CATEGORY_ORDER:
        if name in categories:
            return f"{CATEGORY_EMOJI[name]} {name}"
    return f"{FALLBACK_EMOJI} {FALLBACK_CATEGORY}"


def _parse_collected_at(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _is_recent(mention: dict, now: datetime) -> bool:
    collected = _parse_collected_at(mention.get("collected_at", ""))
    return bool(collected and now - collected <= timedelta(hours=RECENCY_HOURS))


def _score(mention: dict, categories: list[str], own_brands: set, now: datetime) -> int:
    score = 2 * len([c for c in categories if c != FALLBACK_CATEGORY])
    if _is_recent(mention, now):
        score += 3
    if mention.get("brand") in own_brands:
        score += 1
    return score


def build_news_items(mentions: list[dict], own_brands: set, now: datetime | None = None) -> list[dict]:
    """mentions 원본 리스트를 news_card()가 그리는 형태로 변환하고 점수 내림차순으로 정렬한다."""
    now = now or datetime.now()
    items = []
    for m in mentions:
        text = f"{m.get('title', '')} {m.get('snippet', '')}"
        categories = categorize(text)
        collected = _parse_collected_at(m.get("collected_at", ""))
        items.append({
            "score": _score(m, categories, own_brands, now),
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "date": collected.strftime("%Y-%m-%d") if collected else (m.get("collected_at", "") or "")[:10],
            "firm": m.get("brand", ""),
            "collected_at": m.get("collected_at", ""),
            "categories": categories,
            "signal": _signal_label(categories),
            "desc": [m["snippet"]] if m.get("snippet") else ["(요약 없음)"],
            "decision": [
                f"“{m.get('brand', '')}” 관련해 {m.get('channel', '')} 채널에서 감지된 신호입니다."
            ],
            "meta": f"🕒 {m.get('posted_at') or (m.get('collected_at', '') or '')[:16]} · {m.get('channel', '')}",
            "_collected": collected,
        })
    items.sort(key=lambda it: (it["score"], it["_collected"] or datetime.min), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    for i, it in enumerate(items):
        it["medal"] = medals[i] if i < 3 else str(i + 1)
        del it["_collected"]
    return items


def build_metrics(mentions: list[dict], total_count: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    recent_12h = sum(1 for m in mentions if _is_recent(m, now))
    categorized = 0
    ai_signals = 0
    for m in mentions:
        categories = categorize(f"{m.get('title', '')} {m.get('snippet', '')}")
        if categories != [FALLBACK_CATEGORY]:
            categorized += 1
        if "AI" in categories:
            ai_signals += 1
    ratio = round(100 * categorized / len(mentions)) if mentions else 0
    return [
        {"icon": "◫", "value": f"{total_count:,}", "label": "전체 수집"},
        {"icon": "◷", "value": f"{recent_12h:,}", "label": f"{RECENCY_HOURS}시간 내 기사"},
        {"icon": "◎", "value": f"{ai_signals:,}", "label": "AI 관련 신호"},
        {"icon": "↗", "value": f"{ratio}%", "label": "관련 기사 비율"},
    ]


def build_hourly(mentions: list[dict], now: datetime | None = None, window_hours: int = RECENCY_HOURS) -> list[tuple]:
    """now 기준 최근 window_hours시간을 시간 단위로 나눠 수집 건수를 센다 (과거→현재 순)."""
    now = now or datetime.now()
    counts = {}
    for m in mentions:
        collected = _parse_collected_at(m.get("collected_at", ""))
        if collected:
            key = collected.strftime("%Y-%m-%d %H")
            counts[key] = counts.get(key, 0) + 1
    buckets = []
    for i in range(window_hours - 1, -1, -1):
        hour_dt = now - timedelta(hours=i)
        key = hour_dt.strftime("%Y-%m-%d %H")
        buckets.append((f"{hour_dt.hour:02d}시", counts.get(key, 0)))
    return buckets


def build_issue_pulse(mentions: list[dict]) -> tuple:
    """카테고리(일반 제외) 중 가장 많이 매칭된 것과 건수를 반환."""
    counts = {}
    for m in mentions:
        for c in categorize(f"{m.get('title', '')} {m.get('snippet', '')}"):
            if c != FALLBACK_CATEGORY:
                counts[c] = counts.get(c, 0) + 1
    if not counts:
        return ("-", 0)
    return max(counts.items(), key=lambda kv: kv[1])


def build_action_radar(mentions: list[dict]) -> tuple:
    """“신규 도입” 카테고리 매칭 건수와, 그중 가장 많이 언급된 브랜드."""
    brand_counts = {}
    total = 0
    for m in mentions:
        if "신규 도입" in categorize(f"{m.get('title', '')} {m.get('snippet', '')}"):
            total += 1
            brand = m.get("brand", "")
            if brand:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
    top_brand = max(brand_counts.items(), key=lambda kv: kv[1])[0] if brand_counts else ""
    return (total, top_brand)


def build_issues(mentions: list[dict], now: datetime | None = None) -> list[dict]:
    """mentions 각 건을 "부동산사 동향" 페이지의 이슈 카드 1건으로 변환한다.
    실제 이슈 클러스터링(같은 사건 여러 기사 묶기)은 하지 않고, 건별로 1개 카드를 만든다."""
    now = now or datetime.now()
    issues = []
    for m in mentions:
        categories = categorize(f"{m.get('title', '')} {m.get('snippet', '')}")
        primary = next((c for c in CATEGORY_ORDER if c in categories), categories[0])
        bg, fg = CATEGORY_COLORS.get(primary, CATEGORY_COLORS[FALLBACK_CATEGORY])
        collected = _parse_collected_at(m.get("collected_at", ""))
        date_str = collected.strftime("%Y-%m-%d") if collected else (m.get("collected_at", "") or "")[:10]
        issues.append({
            "firm": m.get("brand", ""),
            "cat": f"{CATEGORY_EMOJI.get(primary, FALLBACK_EMOJI)} {primary}",
            "cat_bg": bg,
            "cat_fg": fg,
            "title": m.get("title", ""),
            "count": 1,
            "date": date_str,
            "live": _is_recent(m, now),
            "articles": [(m.get("collected_at", "") or "", m.get("title", ""), m.get("url", ""))],
        })
    return issues


def build_briefings(mentions: list[dict], own_brands: set, limit_days: int = 14) -> list[dict]:
    """mentions를 수집일(collected_at 날짜) 기준으로 묶어 일자별 브리핑 카드를 만든다."""
    by_date: dict[str, list[dict]] = {}
    for m in mentions:
        collected = _parse_collected_at(m.get("collected_at", ""))
        date_str = collected.strftime("%Y-%m-%d") if collected else (m.get("collected_at", "") or "")[:10]
        by_date.setdefault(date_str, []).append(m)

    briefings = []
    for date_str in sorted(by_date.keys(), reverse=True)[:limit_days]:
        day_mentions = by_date[date_str]
        items = build_news_items(day_mentions, own_brands)
        headline = ", ".join(it["title"][:24] for it in items[:2])
        briefings.append({
            "date": date_str,
            "title": "📰 부동산 AI 주요뉴스 브리핑",
            "summary": f"{headline} 등 {len(day_mentions):,}건 선별" if headline else f"{len(day_mentions):,}건 수집",
        })
    return briefings
