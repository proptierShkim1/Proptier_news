"""
hana_p — "AI AGENT" 페이지용 범용 Gemini 대화. summarizer.py와 같은 자격증명(GEMINI_API_KEYS/
GEMINI_MODEL)을 재사용한다.

매 메시지마다 새 genai.Client()로 대화를 재구성한다(이전 히스토리를 seed로 주입) — Streamlit
재실행이 다른 스레드에서 스크립트를 돌릴 수 있어, SDK의 chat 세션 객체를 session_state에
그대로 들고 있다가 재사용하면 내부 HTTP 클라이언트가 닫힌 상태로 남아 "client has been closed"
오류가 나는 걸 실제로 확인했다. 그래서 히스토리는 순수 텍스트로만 들고 있다가, 메시지를 보낼
때마다 새 세션에 주입하는 방식으로 바꿨다 — 여러 키로 failover하기도 이 방식이 더 쉽다.

벡터 검색(vectorizer.search_similar_mentions/search_similar_policy_events)으로 찾은 관련
뉴스·정책 자료는 build_grounding_context()로 텍스트 블록을 만들어 ask()의 context 인자로
주입한다 — 대화 히스토리(화면에 보이는 텍스트)에는 섞이지 않고, 그 턴의 system_instruction에만
추가되므로 매 질문마다 다른 검색 결과를 반영할 수 있다.
"""

from datetime import datetime, timedelta

from google import genai
from google.genai import types

import cached_db
import db
import graph_queries
import news_feed
import policy_feed
import summarizer
import utils

_BASE_SYSTEM_INSTRUCTION = (
    "너는 프롭티어(부동산 AI 프롭테크 기업) 사내에서 쓰는 어시스턴트야. 한국어로 "
    "친근하고 간결하게 답변해."
)
_NO_CONTEXT_NOTE = (
    " 이 질문과 관련된 사내 뉴스·정책 데이터를 찾지 못했으니, 일반적인 지식으로 답하되 "
    "사내 데이터 기반 답변은 아니라는 점을 밝혀줘."
)
_WITH_CONTEXT_NOTE = (
    "\n\n다음은 이 질문과 관련해 사내에서 수집한 뉴스·정책 자료야. 이 자료를 우선 참고해서 "
    "답변하고, 자료에 없는 내용은 지어내지 마. 필요하면 어떤 자료를 참고했는지 간단히 언급해도 돼:\n\n"
)
_WEB_SEARCH_NOTE = (
    " 사내 데이터에서 관련 자료를 찾지 못한 질문이야. 구글 검색으로 최신 정보를 찾아 답변하고, "
    "이 답변은 사내 데이터가 아니라 웹 검색 기반이라는 점을 자연스럽게 밝혀줘."
)
# 벡터 검색 결과 중 가장 가까운(distance가 가장 작은) 항목이 이 값보다 크면(=관련성이
# 약하면) "사내 데이터로 답하기 어려움"으로 판단한다. 실제 관련 질문/무관한 질문 각각
# 몇 개를 gemini-embedding-001 + sqlite-vec(L2 거리)로 실측해 정한 값 — 관련 질문은
# 0.69~0.80대, 무관한 질문은 0.85~0.91대에 몰려 있었다.
_INSUFFICIENT_DISTANCE_THRESHOLD = 0.83

# _STATS_TOOLS(16개 지표 도구)만으로 명백히 답할 수 있는 질문 유형의 신호 키워드 —
# 이런 질문은 벡터 검색(기사 원문 그라운딩)이 필요 없는데도 지금까지 매 메시지마다
# 임베딩 API를 2번(뉴스/정책) 호출하고 있었다. 동시 사용자가 늘수록 이 낭비가
# 커지므로, 명백한 경우에만 건너뛴다 — 애매하면 항상 그라운딩을 시도한다(거짓양성으로
# API를 아끼는 것보다 거짓음성으로 근거를 놓치는 게 더 나쁘다).
_STATS_ONLY_KEYWORDS = (
    "몇 건", "몇건", "몇 개", "몇개", "건수", "개수",
    "api 비용", "api비용", "비용 얼마", "얼마 썼", "얼마나 썼",
    "벡터화 현황", "벡터화 진행률", "벡터화 얼마나", "벡터화 상태",
    "수집 현황", "수집 상태", "실행 현황", "마지막 수집",
    "제일 많이 언급", "가장 많이 언급", "언급 순위", "언급 비교", "언급 추이",
    "추적하는 브랜드", "추적 브랜드", "경쟁사가 뭐", "경쟁사 목록",
    "조회수 높은", "조회수가 높은", "조회수 순위",
    "지난주랑 비교", "이번주랑 비교", "기간 비교",
)


def looks_like_stats_only_question(message: str) -> bool:
    """지표 도구(_STATS_TOOLS)만으로 답할 수 있을 만큼 명백한 통계/집계 질문인지
    가볍게 판별한다. 애매하면 항상 False를 반환해 벡터 검색(그라운딩)을 그대로
    시도하게 한다."""
    text = message.replace(" ", "")
    return any(kw.replace(" ", "") in text for kw in _STATS_ONLY_KEYWORDS)


def has_api_keys() -> bool:
    return bool(summarizer._load_api_keys())


def build_grounding_context(mention_hits: list[dict], policy_hits: list[dict]) -> str:
    """벡터 검색으로 찾은 관련 뉴스/정책 항목을 ask()에 넘길 텍스트 블록으로 만든다.
    둘 다 비어있으면 빈 문자열을 반환한다."""
    lines = []
    for m in mention_hits:
        header = f"- [뉴스] {m.get('title', '')} ({m.get('brand', '')} · {m.get('posted_at') or m.get('collected_at', '')})"
        lines.append(header)
        gist = (m.get("summary") or m.get("content") or m.get("snippet") or "").strip()
        if gist:
            lines.append(f"  {gist[:300]}")
    for p in policy_hits:
        lines.append(f"- [정책] {p.get('title', '')} ({p.get('source', '')} · {p.get('announced_at', '')})")
    return "\n".join(lines)


def _seed_history(history: list[dict]) -> list:
    return [
        types.Content(
            role="user" if turn["role"] == "user" else "model",
            parts=[types.Part(text=turn["content"])],
        )
        for turn in history
    ]


def _send_with_key_failover(system_instruction: str, seeded_history: list, message: str, tools=None) -> str:
    keys = summarizer._load_api_keys()
    if not keys:
        return "GEMINI_API_KEYS가 설정되지 않아 에이전트를 사용할 수 없습니다."

    config = {"system_instruction": system_instruction}
    if tools:
        config["tools"] = tools

    for key in keys:
        try:
            client = genai.Client(api_key=key)
            chat = client.chats.create(
                model=summarizer._model_name(), config=config, history=seeded_history,
            )
            response = chat.send_message(message)
            usage = response.usage_metadata
            db.insert_api_usage(
                "agent_chat", summarizer._model_name(), ok=True,
                prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
                thoughts_tokens=(usage.thoughts_token_count or 0) if usage else 0,
                total_tokens=(usage.total_token_count or 0) if usage else 0,
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception:
            db.insert_api_usage("agent_chat", summarizer._model_name(), ok=False)
            continue
    return "응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."


def get_channel_counts(date: str) -> dict:
    """주어진 날짜에 채널별로 몇 건씩 뉴스가 수집됐는지 알려준다.

    Args:
        date: 조회할 날짜, YYYY-MM-DD 형식 (예: "2026-08-13").

    Returns:
        채널 이름을 키로, 그 채널에서 수집된 건수를 값으로 갖는 딕셔너리.
    """
    mentions = cached_db.get_mentions_by_collected_date(date)
    counts: dict[str, int] = {}
    for m in mentions:
        counts[m["channel"]] = counts.get(m["channel"], 0) + 1
    return counts


def get_overview_stats() -> dict:
    """사내 데이터 수집 현황을 한눈에 보여주는 전체 지표 스냅샷을 반환한다.

    Returns:
        총 뉴스 수집 건수(total_mentions), 총 정책 보도자료 수집 건수(total_policy_events),
        벡터 검색 색인이 완료된 뉴스/정책 건수(vectorized_mentions/vectorized_policy_events),
        확정된 브리핑 날짜 수(archived_briefing_days)를 담은 딕셔너리.
    """
    return {
        "total_mentions": cached_db.count_mentions(),
        "total_policy_events": cached_db.count_policy_events(),
        "vectorized_mentions": cached_db.count_mention_vector_index(),
        "vectorized_policy_events": cached_db.count_policy_vector_index(),
        "archived_briefing_days": len(cached_db.get_archived_briefing_dates()),
    }


def get_brand_mention_count(brand: str) -> int:
    """특정 브랜드(회사명)가 지금까지 누적으로 몇 번 언급됐는지 알려준다.

    Args:
        brand: 조회할 브랜드명 (예: "직방", "프롭티어", "다방").

    Returns:
        해당 브랜드로 수집된 mentions 누적 건수.
    """
    return cached_db.count_mentions_by_brand(brand)


def get_policy_source_counts() -> dict:
    """정부 정책 보도자료가 기관(소스)별로 몇 건씩 수집됐는지 알려준다.

    Returns:
        기관명(예: "국토부", "LH", "한국부동산원")을 키로, 수집 건수를 값으로 갖는 딕셔너리.
    """
    return cached_db.get_policy_source_counts()


def get_briefing_highlights(date: str) -> dict:
    """특정 날짜에 확정된(아카이빙된) 브리핑의 실제 내용을 알려준다 — 단순 건수가 아니라
    그날의 채널별 주요 뉴스, 프롭티어 관련 뉴스, 경쟁사 동향, 시장 동향을 그대로 담고
    있다. 아직 확정 안 된 날짜(오늘 등)라도 그 시점까지 수집된 데이터로 즉석에서 같은
    내용을 계산해 반환한다.

    Args:
        date: 조회할 날짜, YYYY-MM-DD 형식.

    Returns:
        해당 날짜에 데이터가 전혀 없으면 {"found": False}. 있으면 {"found": True,
        "total_count": int, "channel_counts": {...}, "channel_top_news": {...},
        "own_brand_news": [...], "competitor_news": [...], "market_news": [...]}.
    """
    content = cached_db.get_briefing_archive(date)
    if content is None:
        day_mentions = cached_db.get_mentions_by_collected_date(date)
        if not day_mentions:
            return {"found": False}
        content = news_feed.build_briefing_archive_content(
            day_mentions, news_feed.own_brand_names(),
            news_feed.competitor_brand_names(), news_feed.market_brand_names(),
        )
    return {
        "found": True,
        "total_count": content["total_count"],
        "channel_counts": content["channel_counts"],
        "channel_top_news": content["channel_top_news"],
        "own_brand_news": content["own_brand_news"],
        "competitor_news": content["competitor_news"],
        "market_news": content["market_news"],
    }


def get_collection_health() -> dict:
    """수집 채널별로 가장 최근 실행이 언제였고 성공했는지 알려준다 — 신규 게시물(네이버·
    구글·다음·커뮤니티 통합)/네이버뉴스API/매경API/정부 정책(7개 기관 통합) 각각 가장
    최근 배치 1건 기준.

    Returns:
        채널 그룹명을 키로, {"last_run_at": "YYYY-MM-DD HH:MM:SS", "trigger": "수동|자동",
        "ok": bool, "message": str} 값을 갖는 딕셔너리. 한 번도 실행 안 된 채널은 빠진다.
    """
    result = {}
    channel_groups = {
        "신규 게시물": ["네이버", "구글", "다음", "커뮤니티"],
        "네이버뉴스API": ["네이버뉴스API"],
        "매경API": ["매경API"],
    }
    for label, channels in channel_groups.items():
        batches = cached_db.get_run_batches(limit=1, channels=tuple(channels))
        if batches:
            b = batches[0]
            result[label] = {
                "last_run_at": b["ran_at"], "trigger": b["trigger"],
                "ok": bool(b["ok"]), "message": b["message"],
            }
    policy_batches = cached_db.get_policy_run_batches(limit=1)
    if policy_batches:
        b = policy_batches[0]
        result["정부 정책"] = {
            "last_run_at": b["ran_at"], "trigger": b["trigger"],
            "ok": bool(b["ok"]), "message": b["message"],
        }
    return result


def compare_brand_mentions(brands: list[str], days: int = 30) -> dict:
    """여러 브랜드의 최근 N일간 언급 건수를 비교한다 — "직방이랑 프롭티어 이번 달 언급
    추이 비교해줘" 같은 질문에 쓴다.

    Args:
        brands: 비교할 브랜드명 리스트 (예: ["직방", "프롭티어"]).
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        브랜드명을 키로, 최근 days일간 언급 건수를 값으로 갖는 딕셔너리.
    """
    return {brand: cached_db.count_mentions_by_brand_since(brand, days) for brand in brands}


def get_vectorization_status() -> dict:
    """벡터화(임베딩 생성, AI AGENT 검색의 기반) 진행 현황을 알려준다 — 전체 건수 대비
    아직 벡터화 안 된 건수.

    Returns:
        {"mentions_total": int, "mentions_pending": int, "policy_events_total": int,
        "policy_events_pending": int}.
    """
    return {
        "mentions_total": cached_db.count_mentions(),
        "mentions_pending": cached_db.count_mentions_without_embedding(),
        "policy_events_total": cached_db.count_policy_events(),
        "policy_events_pending": cached_db.count_policy_events_without_embedding(),
    }


def get_top_mentioned_brands(days: int = 30, limit: int = 5) -> list[dict]:
    """최근 N일간 가장 많이 언급된 브랜드 순위를 알려준다 — 브랜드 이름을 몰라도 "요즘
    누가 제일 핫해?" 같은 질문에 답할 수 있다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).
        limit: 몇 개까지 보여줄지 (기본 5개).

    Returns:
        [{"brand": str, "count": int}, ...] 언급 건수 내림차순.
    """
    return cached_db.get_top_mentioned_brands(days=days, limit=limit)


def get_news_category_counts(days: int = 30) -> dict:
    """최근 N일간 수집된 뉴스가 카테고리별(신규 도입/AI/부동산AI/매물/시세·감정/정책/해외/
    리포트)로 몇 건씩 해당하는지 알려준다. 한 기사가 여러 카테고리에 동시에 해당할 수
    있어 합계가 전체 건수보다 클 수 있다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        카테고리명을 키로, 해당 건수를 값으로 갖는 딕셔너리.
    """
    mentions = cached_db.get_mentions_since(days)
    counts: dict[str, int] = {}
    for m in mentions:
        text = f"{m.get('title', '')} {m.get('snippet', '')}"
        for cat in news_feed.categorize(text):
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def get_policy_category_counts(days: int = 30) -> dict:
    """최근 N일간 수집된 정부 정책 보도자료가 카테고리별(규제·법령/지원·사업/통계·조사/
    조직·인사/행사·홍보)로 몇 건씩 해당하는지 알려준다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        카테고리명을 키로, 해당 건수를 값으로 갖는 딕셔너리.
    """
    events = cached_db.get_policy_events_since(days)
    counts: dict[str, int] = {}
    for e in events:
        for cat in policy_feed.categorize(e.get("title", "")):
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def compare_collection_periods(period_days: int = 7) -> dict:
    """최근 period_days일과 그 직전 period_days일의 전체 뉴스 수집 건수를 비교한다 —
    "이번주랑 지난주 비교해줘" 같은 질문에 쓴다.

    Args:
        period_days: 한 구간의 길이(일). 기본 7일(주간 비교).

    Returns:
        {"recent_period": {"days": int, "count": int}, "previous_period": {"days": int,
        "count": int}, "change": int, "change_pct": float | None} — change_pct는 직전
        구간이 0건이면 계산 불가능하므로 None.
    """
    recent = cached_db.count_mentions_between(period_days, 0)
    previous = cached_db.count_mentions_between(period_days * 2, period_days)
    change = recent - previous
    change_pct = round((change / previous) * 100, 1) if previous else None
    return {
        "recent_period": {"days": period_days, "count": recent},
        "previous_period": {"days": period_days, "count": previous},
        "change": change,
        "change_pct": change_pct,
    }


# views/settings.py의 "API 사용량" 탭과 동일한 추정 단가(USD/100만 토큰) — 하나를
# 바꾸면 다른 쪽도 같이 갱신할 것.
_PRICE_PER_1M_INPUT_USD = 0.30
_PRICE_PER_1M_OUTPUT_USD = 2.50


def get_api_cost_summary(days: int = 30) -> dict:
    """Gemini API 호출량과 추정 비용을 알려준다 — "이번 달 API 비용 얼마야?" 같은 질문에
    쓴다. 기능별(summarizer=기사요약/agent_chat=AI AGENT 대화/vectorizer=임베딩) 호출
    수·토큰·추정 비용과 전체 합계를 담는다. 비용은 공개 요금 기준 추정치이며 실제
    청구 금액과 다를 수 있다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        {"by_feature": {기능명: {"calls": int, "tokens": int, "failed": int,
        "estimated_cost_usd": float}}, "total_calls": int, "total_tokens": int,
        "total_estimated_cost_usd": float}
    """
    summary = cached_db.get_api_usage_summary(days=days)
    by_feature = {}
    total_cost = 0.0
    total_calls = 0
    total_tokens = 0
    for feature, v in summary.items():
        cost = (
            (v["prompt_tokens"] / 1_000_000) * _PRICE_PER_1M_INPUT_USD
            + (v["output_tokens"] / 1_000_000) * _PRICE_PER_1M_OUTPUT_USD
        )
        by_feature[feature] = {
            "calls": v["calls"], "tokens": v["tokens"], "failed": v["failed"],
            "estimated_cost_usd": round(cost, 4),
        }
        total_cost += cost
        total_calls += v["calls"]
        total_tokens += v["tokens"]
    return {
        "by_feature": by_feature,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_estimated_cost_usd": round(total_cost, 4),
    }


def get_tracked_brands() -> dict:
    """현재 시스템이 수집하도록 등록된 브랜드/키워드 목록을 역할별로 알려준다 — "지금
    우리가 추적하는 경쟁사가 뭐야?" 같은 질문에 쓴다.

    Returns:
        {"own": [...], "competitor": [...], "market": [...]} — 각 리스트는 브랜드명.
    """
    cfg = utils.load_keywords()
    result = {"own": [], "competitor": [], "market": []}
    for b in cfg.get("brands", []):
        role = b.get("role")
        if role in result:
            result[role].append(b["name"])
    return result


def get_pdf_report_stats(days: int = 30) -> dict:
    """최근 N일간 PDF 보고서가 몇 번 생성됐는지 알려준다. 개인별 접속 IP는 노출하지
    않고 전체 건수만 집계한다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        {"count": int}
    """
    return {"count": cached_db.count_activity_log_by_action("PDF 생성", days=days)}


def get_top_viewed_policy_events(limit: int = 5) -> list[dict]:
    """조회수가 가장 높은 정책 보도자료 상위 N건을 알려준다.

    Args:
        limit: 몇 건까지 보여줄지 (기본 5건).

    Returns:
        [{"title": str, "source": str, "view_count": int, "announced_at": str}, ...]
        조회수 내림차순.
    """
    return cached_db.get_top_viewed_policy_events(limit=limit)


def search_mentions(keyword: str = "", brand: str = "", days: int = 30, limit: int = 5) -> list[dict]:
    """수집된 뉴스 기사를 키워드/브랜드/기간으로 검색해 실제 기사 목록(제목·링크 등)을
    반환한다 — 다른 지표 도구들과 달리 건수가 아니라 개별 기사 내용을 준다. "직방 관련
    최근 기사 보여줘", "이번주 매물 관련 기사 뭐 있어" 같은 질문에 쓴다.

    Args:
        keyword: 제목·요약에 모두 포함돼야 하는 검색어 (여러 단어는 띄어쓰기로 구분,
            대소문자 구분 안 함). 비우면 키워드로 거르지 않는다.
        brand: 특정 브랜드로 제한 (예: "직방"). 비우면 전체 브랜드 대상.
        days: 최근 며칠간을 볼지 (기본 30일).
        limit: 몇 건까지 보여줄지 (기본 5건).

    Returns:
        [{"title": str, "url": str, "channel": str, "brand": str, "collected_at": str}, ...]
        최신순. 조건에 맞는 기사가 없으면 빈 리스트.
    """
    mentions = cached_db.get_mentions(brand=brand, limit=3000)
    terms = keyword.lower().split() if keyword else []
    if terms:
        mentions = [
            m for m in mentions
            if all(t in f"{m.get('title', '')} {m.get('snippet', '')}".lower() for t in terms)
        ]
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    mentions = [m for m in mentions if (m.get("collected_at") or "") >= cutoff]
    mentions.sort(key=lambda m: m.get("collected_at", ""), reverse=True)
    return [
        {
            "title": m["title"], "url": m["url"], "channel": m["channel"],
            "brand": m["brand"], "collected_at": m["collected_at"],
        }
        for m in mentions[:limit]
    ]


def get_brand_mention_trend(brand: str, days: int = 30) -> list[dict]:
    """특정 브랜드의 언급 건수가 날짜별로 어떻게 변해왔는지 알려준다 — compare_brand_mentions는
    기간 합계 하나만 주는데, "이번 달 프롭티어 언급 추이 일자별로 보여줘"처럼 날짜별 흐름이
    필요한 질문엔 이 도구를 쓴다.

    Args:
        brand: 조회할 브랜드명.
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        [{"date": "YYYY-MM-DD", "count": int}, ...] 날짜 오름차순. 언급이 없던 날짜는
        포함되지 않는다.
    """
    mentions = cached_db.get_mentions_since(days)
    counts: dict[str, int] = {}
    for m in mentions:
        if m.get("brand") != brand:
            continue
        date = (m.get("collected_at") or "")[:10]
        if date:
            counts[date] = counts.get(date, 0) + 1
    return [{"date": d, "count": c} for d, c in sorted(counts.items())]


def get_trending_brands(recent_days: int = 3, baseline_days: int = 30, limit: int = 5) -> list[dict]:
    """평소(baseline_days일 일평균) 대비 최근(recent_days일) 언급이 급증한 브랜드를 찾는다
    — "요즘 갑자기 뜨는 이슈 뭐야" 같은 질문에 쓴다. mentions에는 정책 보도자료와 달리
    자체 조회수 데이터가 없어(외부 사이트 기사라 조회수를 집계하지 않음), "인기"가 아니라
    "평소 대비 급증"을 화제성 지표로 대신 쓴다.

    Args:
        recent_days: 급증 여부를 볼 최근 기간 (기본 3일).
        baseline_days: 비교 기준이 될 전체 기간 (기본 30일, recent_days를 포함).
        limit: 몇 개까지 보여줄지 (기본 5개).

    Returns:
        [{"brand": str, "recent_count": int, "baseline_daily_avg": float,
        "spike_ratio": float}, ...] spike_ratio 내림차순. 최근 기간에 언급이 아예 없는
        브랜드는 제외된다. spike_ratio가 클수록 평소보다 갑자기 많이 언급됐다는 뜻이다.
    """
    recent = {b["brand"]: b["count"] for b in cached_db.get_top_mentioned_brands(days=recent_days, limit=1000)}
    baseline = {b["brand"]: b["count"] for b in cached_db.get_top_mentioned_brands(days=baseline_days, limit=1000)}
    prior_days = max(baseline_days - recent_days, 1)
    results = []
    for brand, recent_count in recent.items():
        prior_count = max(baseline.get(brand, recent_count) - recent_count, 0)
        baseline_daily_avg = prior_count / prior_days
        recent_daily_avg = recent_count / recent_days
        spike_ratio = recent_daily_avg / baseline_daily_avg if baseline_daily_avg > 0 else recent_daily_avg
        results.append({
            "brand": brand, "recent_count": recent_count,
            "baseline_daily_avg": round(baseline_daily_avg, 2),
            "spike_ratio": round(spike_ratio, 2),
        })
    results.sort(key=lambda r: r["spike_ratio"], reverse=True)
    return results[:limit]


_STATS_TOOLS = [
    get_channel_counts, get_overview_stats, get_brand_mention_count, get_policy_source_counts,
    get_briefing_highlights, get_collection_health, compare_brand_mentions, get_vectorization_status,
    get_top_mentioned_brands, get_news_category_counts, get_policy_category_counts,
    compare_collection_periods, get_api_cost_summary, get_tracked_brands, get_pdf_report_stats,
    get_top_viewed_policy_events, search_mentions, get_brand_mention_trend, get_trending_brands,
    graph_queries.category_alignment_counts, graph_queries.policy_event_mention_impact,
    graph_queries.brand_role_category_breakdown,
]


def is_grounding_sufficient(
    mention_hits: list[dict], policy_hits: list[dict],
    threshold: float = _INSUFFICIENT_DISTANCE_THRESHOLD,
) -> bool:
    """벡터 검색 결과 중 가장 가까운(distance가 가장 작은) 항목이 threshold 이하면 사내
    데이터로 답변 가능하다고 판단한다. 검색 결과가 아예 없으면 False."""
    distances = [h["distance"] for h in mention_hits + policy_hits if "distance" in h]
    if not distances:
        return False
    return min(distances) <= threshold


def ask(history: list[dict], message: str, context: str = "") -> str:
    """history는 이번 메시지를 제외한 이전 턴들 [{"role": "user"|"assistant", "content": str}, ...].
    context가 있으면 이번 턴의 system_instruction에 참고 자료로 덧붙인다(build_grounding_context
    결과). 매번 새 Client/chat 세션을 만들어 history를 주입한 뒤 message를 보내고 응답 텍스트를
    반환한다. 키가 없거나 모든 키 호출이 실패해도 예외를 던지지 않고 에러 메시지 문자열을 반환한다.

    _STATS_TOOLS(채널별 수집 건수·전체 현황·브랜드 언급 건수·정책 소스별 건수)를 함수
    호출 도구로 붙여서, 벡터 검색으로는 답할 수 없는 집계/통계 질문("오늘 채널별로 몇
    건씩 모였어?" 등)에도 실제 숫자로 답할 수 있게 한다. 오늘 날짜를 시스템 인스트럭션에
    명시해, "오늘"/"어제" 같은 상대 표현을 모델이 직접 절대 날짜로 변환해 도구를 호출할
    수 있게 한다."""
    today_note = f" 오늘 날짜는 {datetime.now().strftime('%Y-%m-%d')}이야."
    system_instruction = _BASE_SYSTEM_INSTRUCTION + today_note
    system_instruction += _WITH_CONTEXT_NOTE + context if context else _NO_CONTEXT_NOTE
    return _send_with_key_failover(system_instruction, _seed_history(history), message, tools=_STATS_TOOLS)


def ask_with_web_search(history: list[dict], message: str) -> str:
    """사내 데이터로 답하기 어려운 질문(is_grounding_sufficient가 False)을 구글 검색
    그라운딩으로 다시 답변한다. ask()와 동일한 세션 재구성/키 failover를 쓰되, 사내 자료
    context 대신 google_search 도구를 붙인다."""
    system_instruction = _BASE_SYSTEM_INSTRUCTION + _WEB_SEARCH_NOTE
    tools = [types.Tool(google_search=types.GoogleSearch())]
    return _send_with_key_failover(system_instruction, _seed_history(history), message, tools=tools)
