"""
hana_p — db.py 조회를 짧은 TTL로 캐싱한다. Streamlit은 위젯 값이 바뀔 때마다(검색어 입력,
필터 변경, 브리핑 날짜 선택 등) 스크립트를 처음부터 다시 실행하는데, 이 앱은 지금까지 그때마다
DB를 다시 조회하고 카테고리 분류·클러스터링까지 처음부터 재계산했다. 캐시가 없으면 동시에
여러 사용자가 접속했을 때도 같은 조회/계산이 그만큼 배로 반복된다.

channels는 리스트라 해시 불가능하므로 tuple로 받는다 — 호출부에서 변환해서 넘겨야 한다.

자동 배치 수집(신규 게시물/정책/네이버뉴스/매경 API)이 끝나면 collector.py가 각 백그라운드
작업의 finally 블록에서 clear()를 호출해 즉시 무효화한다 — 2026-08-31, 사용자가 "배치 돌고
F5 누르면 바로 신규 데이터가 나와야 하는 것 아니냐"고 물어 확인해보니 배치 완료 시점에 캐시를
비우는 처리가 없어서 최대 TTL(60초)만큼 지연될 수 있었다. 그 외 관리자의 수동 삭제/백필/설정
변경 등도 마찬가지로 해당 작업 뒤에 clear()를 호출해 캐시를 바로 비운다.
"""

import streamlit as st

import db


@st.cache_data(ttl=60, show_spinner=False)
def get_mentions(limit: int, channels: tuple | None = None, brand: str = "") -> list[dict]:
    return db.get_mentions(
        limit=limit, channels=list(channels) if channels is not None else None, brand=brand,
    )


@st.cache_data(ttl=60, show_spinner=False)
def get_policy_events(limit: int) -> list[dict]:
    return db.get_policy_events(limit=limit)


@st.cache_data(ttl=30, show_spinner=False)
def count_mentions() -> int:
    return db.count_mentions()


@st.cache_data(ttl=30, show_spinner=False)
def count_policy_events() -> int:
    return db.count_policy_events()


# ── AI AGENT 지표 도구용 캐시 ─────────────────────────────────────────────
# agent_chat.py의 _STATS_TOOLS는 매 채팅 메시지마다 그대로 db.py를 조회했는데,
# 동시에 여러 사용자가 비슷한 질문("오늘 몇 건 수집됐어?" 등)을 하면 그만큼 DB 재조회가
# 반복된다. 도구 함수 자체는 Gemini가 시그니처/독스트링을 그대로 읽어 스키마를 만드므로
# 손대지 않고, 그 안에서 부르는 db.* 호출만 여기 캐시로 바꿔치기한다.

@st.cache_data(ttl=60, show_spinner=False)
def get_mentions_by_collected_date(date: str) -> list[dict]:
    return db.get_mentions_by_collected_date(date)


@st.cache_data(ttl=60, show_spinner=False)
def count_mention_vector_index() -> int:
    return db.count_mention_vector_index()


@st.cache_data(ttl=60, show_spinner=False)
def count_policy_vector_index() -> int:
    return db.count_policy_vector_index()


@st.cache_data(ttl=60, show_spinner=False)
def get_archived_briefing_dates() -> set:
    return db.get_archived_briefing_dates()


@st.cache_data(ttl=60, show_spinner=False)
def get_distinct_mention_dates() -> set:
    return db.get_distinct_mention_dates()


@st.cache_data(ttl=60, show_spinner=False)
def get_earliest_mention_date() -> str | None:
    return db.get_earliest_mention_date()


@st.cache_data(ttl=60, show_spinner=False)
def count_mentions_by_brand(brand: str) -> int:
    return db.count_mentions_by_brand(brand)


@st.cache_data(ttl=60, show_spinner=False)
def get_policy_source_counts() -> dict:
    return db.get_policy_source_counts()


@st.cache_data(ttl=60, show_spinner=False)
def get_briefing_archive(date: str):
    return db.get_briefing_archive(date)


@st.cache_data(ttl=60, show_spinner=False)
def get_run_batches(limit: int, channels: tuple | None = None) -> list[dict]:
    return db.get_run_batches(limit=limit, channels=list(channels) if channels is not None else None)


@st.cache_data(ttl=60, show_spinner=False)
def get_policy_run_batches(limit: int) -> list[dict]:
    return db.get_policy_run_batches(limit=limit)


@st.cache_data(ttl=60, show_spinner=False)
def count_mentions_by_brand_since(brand: str, days: int) -> int:
    return db.count_mentions_by_brand_since(brand, days)


@st.cache_data(ttl=60, show_spinner=False)
def count_mentions_without_embedding() -> int:
    return db.count_mentions_without_embedding()


@st.cache_data(ttl=60, show_spinner=False)
def count_policy_events_without_embedding() -> int:
    return db.count_policy_events_without_embedding()


@st.cache_data(ttl=60, show_spinner=False)
def get_top_mentioned_brands(days: int, limit: int) -> list[dict]:
    return db.get_top_mentioned_brands(days=days, limit=limit)


@st.cache_data(ttl=60, show_spinner=False)
def get_mentions_since(days: int) -> list[dict]:
    return db.get_mentions_since(days)


@st.cache_data(ttl=60, show_spinner=False)
def get_policy_events_since(days: int) -> list[dict]:
    return db.get_policy_events_since(days)


@st.cache_data(ttl=60, show_spinner=False)
def count_mentions_between(start_days_ago: int, end_days_ago: int) -> int:
    return db.count_mentions_between(start_days_ago, end_days_ago)


@st.cache_data(ttl=60, show_spinner=False)
def get_mentions_between(start_days_ago: int, end_days_ago: int) -> list[dict]:
    return db.get_mentions_between(start_days_ago, end_days_ago)


@st.cache_data(ttl=60, show_spinner=False)
def get_api_usage_summary(days: int) -> dict:
    return db.get_api_usage_summary(days=days)


@st.cache_data(ttl=60, show_spinner=False)
def count_activity_log_by_action(action: str, days: int) -> int:
    return db.count_activity_log_by_action(action, days=days)


@st.cache_data(ttl=60, show_spinner=False)
def get_top_viewed_policy_events(limit: int) -> list[dict]:
    return db.get_top_viewed_policy_events(limit=limit)


def clear() -> None:
    """관리자가 데이터를 수정한 뒤(삭제·백필·재수집 등) 호출해 캐시를 즉시 무효화한다."""
    get_mentions.clear()
    get_policy_events.clear()
    count_mentions.clear()
    count_policy_events.clear()
    get_mentions_by_collected_date.clear()
    count_mention_vector_index.clear()
    count_policy_vector_index.clear()
    get_archived_briefing_dates.clear()
    get_distinct_mention_dates.clear()
    get_earliest_mention_date.clear()
    count_mentions_by_brand.clear()
    get_policy_source_counts.clear()
    get_briefing_archive.clear()
    get_run_batches.clear()
    get_policy_run_batches.clear()
    count_mentions_by_brand_since.clear()
    count_mentions_without_embedding.clear()
    count_policy_events_without_embedding.clear()
    get_top_mentioned_brands.clear()
    get_mentions_since.clear()
    get_policy_events_since.clear()
    count_mentions_between.clear()
    get_mentions_between.clear()
    get_api_usage_summary.clear()
    count_activity_log_by_action.clear()
    get_top_viewed_policy_events.clear()
