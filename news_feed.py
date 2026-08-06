"""
hana_p — mentions 원본 데이터를 "오늘의 뉴스" 화면 표시 형태로 가공.
카테고리 분류·점수·메달은 실제 수집 데이터에 없는 필드라 키워드 기반 휴리스틱으로 계산한다.
"""

import re
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
CLUSTER_SIMILARITY_THRESHOLD = 0.35
CLUSTER_WINDOW_HOURS = 48
_TITLE_STOPWORDS = {
    "의", "가", "이", "은", "는", "을", "를", "에", "에서", "와", "과", "도", "만",
    "등", "것", "수", "위해", "관련", "대한", "이번", "오늘",
}
_TITLE_TOKEN_RE = re.compile(r"\[[^\]]*\]|[^\w가-힣\s]")
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

        snippet = (m.get("snippet") or "").strip()
        title = (m.get("title") or "").strip()
        if snippet and snippet != title:
            desc = [snippet]
        else:
            desc = [f"{m.get('channel', '')} 채널에서 수집된 기사입니다 · 원문 링크에서 전체 내용을 확인하세요."]

        real_categories = [c for c in categories if c != FALLBACK_CATEGORY]
        cat_line = (
            f"{', '.join(real_categories)} 카테고리에 해당하는 기사로 선별되었습니다."
            if real_categories else
            "카테고리 키워드와 직접 매칭되지는 않았지만 관련 신호로 수집되었습니다."
        )
        recency_line = (
            f"최근 {RECENCY_HOURS}시간 내 수집되어 신선도가 높습니다."
            if _is_recent(m, now) else
            "누적 수집 데이터 중 상위 신호로 선정되었습니다."
        )

        items.append({
            "score": _score(m, categories, own_brands, now),
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "date": collected.strftime("%Y-%m-%d") if collected else (m.get("collected_at", "") or "")[:10],
            "firm": m.get("brand", ""),
            "collected_at": m.get("collected_at", ""),
            "categories": categories,
            "signal": _signal_label(categories),
            "desc": desc,
            "decision": [f"{cat_line} {recency_line}"],
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


def _title_tokens(title: str) -> set:
    """제목에서 [태그]와 문장부호를 제거하고, 2글자 이상·불용어가 아닌 단어만 남긴다."""
    cleaned = _TITLE_TOKEN_RE.sub(" ", title)
    return {t for t in cleaned.split() if len(t) >= 2 and t not in _TITLE_STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _cluster_mentions(mentions: list[dict]) -> list[list[dict]]:
    """같은 브랜드 + 제목 단어가 많이 겹침(자카드 유사도) + CLUSTER_WINDOW_HOURS 이내에
    수집된 기사를 하나의 이슈로 묶는다. 실제 동일 사건 판정이 아니라 가벼운 휴리스틱이라,
    표현이 많이 다른 헤드라인은 같은 사건이어도 묶이지 않을 수 있다."""
    ordered = sorted(mentions, key=lambda m: m.get("collected_at") or "")
    clusters: list[dict] = []
    for m in ordered:
        collected = _parse_collected_at(m.get("collected_at", ""))
        tokens = _title_tokens(m.get("title", ""))
        best = None
        for c in clusters:
            if c["brand"] != m.get("brand"):
                continue
            last_collected = c["last_collected"]
            if last_collected and collected:
                gap_hours = abs((collected - last_collected).total_seconds()) / 3600
                if gap_hours > CLUSTER_WINDOW_HOURS:
                    continue
            if _jaccard(tokens, c["tokens"]) >= CLUSTER_SIMILARITY_THRESHOLD:
                best = c
                break
        if best is not None:
            best["mentions"].append(m)
            best["tokens"] |= tokens
            if collected and (best["last_collected"] is None or collected > best["last_collected"]):
                best["last_collected"] = collected
        else:
            clusters.append({
                "brand": m.get("brand"), "tokens": tokens,
                "mentions": [m], "last_collected": collected,
            })
    return [c["mentions"] for c in clusters]


def build_issues(mentions: list[dict], now: datetime | None = None) -> list[dict]:
    """mentions를 (브랜드+제목 유사도+시간창) 기준으로 클러스터링해 "부동산사 동향"
    페이지의 이슈 카드로 변환한다. 한 이슈 카드가 여러 기사를 대표할 수 있다."""
    now = now or datetime.now()
    issues = []
    for cluster in _cluster_mentions(mentions):
        cluster = sorted(cluster, key=lambda m: m.get("collected_at") or "")
        rep = cluster[0]
        categories = categorize(f"{rep.get('title', '')} {rep.get('snippet', '')}")
        primary = next((c for c in CATEGORY_ORDER if c in categories), categories[0])
        bg, fg = CATEGORY_COLORS.get(primary, CATEGORY_COLORS[FALLBACK_CATEGORY])
        rep_collected = _parse_collected_at(rep.get("collected_at", ""))
        date_str = rep_collected.strftime("%Y-%m-%d") if rep_collected else (rep.get("collected_at", "") or "")[:10]
        live = any(_is_recent(m, now) for m in cluster)
        articles = sorted(
            [(m.get("collected_at", "") or "", m.get("title", ""), m.get("url", "")) for m in cluster],
            reverse=True,
        )
        issues.append({
            "firm": rep.get("brand", ""),
            "cat": f"{CATEGORY_EMOJI.get(primary, FALLBACK_EMOJI)} {primary}",
            "cat_bg": bg,
            "cat_fg": fg,
            "title": rep.get("title", ""),
            "count": len(cluster),
            "date": date_str,
            "live": live,
            "articles": articles,
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
