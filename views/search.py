from datetime import datetime, timedelta

import streamlit as st

import cached_db
import db
import news_feed
import theme

_PERIOD_DAYS = {"전체": None, "최근 90일": 90, "최근 30일": 30, "최근 7일": 7}


def render():
    theme.hero(
        "\U0001F50D 지난 뉴스 검색",
        f"누적 수집 {cached_db.count_mentions():,}건 · 키워드·기간·부동산사로 바로 필터링",
    )

    c1, c2, c3 = st.columns([2, 1.3, 1])
    with c1:
        period = st.segmented_control("기간", list(_PERIOD_DAYS.keys()), default="전체")
    with c2:
        firm = st.selectbox("\U0001F3E2 부동산사", ["전체"] + news_feed.all_brand_names())
    with c3:
        sort = st.selectbox("↕️ 정렬", ["최신순", "점수순"])
    query = st.text_input(
        "검색어", placeholder="검색어 입력 — 여러 단어는 띄어쓰기 (모두 포함된 기사만 표시)",
        label_visibility="collapsed",
    )

    if query and st.session_state.get("_last_logged_search") != query:
        db.log_activity(st.session_state.get("_client_ip", ""), "뉴스 검색", "검색", query)
        st.session_state["_last_logged_search"] = query

    period = period or "전체"
    mentions = cached_db.get_mentions(
        brand="" if firm == "전체" else firm,
        channels=tuple(news_feed.enabled_channels()),
        limit=news_feed.BROAD_LIMIT,
    )

    terms = query.lower().split() if query else []
    if terms:
        mentions = [
            m for m in mentions
            if all(t in f"{m.get('title', '')} {m.get('snippet', '')}".lower() for t in terms)
        ]

    days = _PERIOD_DAYS[period]
    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        mentions = [m for m in mentions if (m.get("collected_at") or "") >= cutoff]

    news_items = news_feed.build_news_items(mentions, news_feed.own_brand_names())
    if sort == "점수순":
        news_items = sorted(news_items, key=lambda n: -n["score"])
    else:
        news_items = sorted(news_items, key=lambda n: n["collected_at"], reverse=True)

    caption_col, help_col = st.columns([10, 1], vertical_alignment="center")
    caption_col.caption(f"검색 결과 {len(news_items):,}건 · 기간: {period} · 부동산사: {firm}")
    with help_col:
        with st.popover("❓"):
            st.markdown(news_feed.category_legend_markdown())

    if not news_items:
        st.info("조건에 맞는 기사가 없습니다. 검색어나 필터를 바꿔보세요.")
    for i, item in enumerate(news_items[:news_feed.DISPLAY_LIMIT], start=1):
        theme.news_card(item, item["medal"])

    theme.footer("실제 수집 데이터(mentions) 기반 검색")
