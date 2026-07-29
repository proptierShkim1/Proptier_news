from datetime import datetime, timedelta

import streamlit as st

import theme
from data import FIRMS, NEWS, TODAY

_PERIOD_DAYS = {"전체": None, "최근 90일": 90, "최근 30일": 30, "최근 7일": 7}


def render():
    theme.hero(
        "\U0001F50D 지난 뉴스 검색",
        "누적 DB 30,000건 (샘플) · 키워드·기간·부동산사로 바로 필터링",
    )

    st.markdown('<div class="sc-box">', unsafe_allow_html=True)
    query = st.text_input(
        "검색어", placeholder="검색어 입력 — 여러 단어는 띄어쓰기 (모두 포함된 기사만 표시)",
        label_visibility="collapsed",
    )
    c1, c2, c3 = st.columns([2, 1.3, 1])
    with c1:
        period = st.segmented_control("기간", list(_PERIOD_DAYS.keys()), default="전체")
    with c2:
        firm = st.selectbox("\U0001F3E2 부동산사", ["전체"] + FIRMS)
    with c3:
        sort = st.selectbox("↕️ 정렬", ["최신순", "점수순"])
    st.markdown('</div>', unsafe_allow_html=True)

    period = period or "전체"
    terms = query.lower().split() if query else []
    results = [
        n for n in NEWS
        if not terms or all(t in (n["title"] + " ".join(n["desc"])).lower() for t in terms)
    ]

    if firm != "전체":
        results = [n for n in results if n.get("firm") == firm]

    days = _PERIOD_DAYS[period]
    if days is not None:
        cutoff = TODAY - timedelta(days=days)
        results = [
            n for n in results
            if datetime.strptime(n["date"], "%Y-%m-%d").date() >= cutoff
        ]

    if sort == "점수순":
        results = sorted(results, key=lambda n: -n["score"])
    else:
        results = sorted(results, key=lambda n: n["date"], reverse=True)

    st.caption(f"검색 결과 {len(results)}건 · 기간: {period} · 부동산사: {firm}")

    if not results:
        st.info("조건에 맞는 기사가 없습니다. 검색어나 필터를 바꿔보세요.")
    for i, item in enumerate(results, start=1):
        theme.news_card(item, i)

    theme.footer("news.db 최근 180일 기사 수록 (샘플)")
