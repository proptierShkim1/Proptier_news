import streamlit as st

import theme
from data import METRICS, HOURLY, CATEGORY_NAMES, NEWS


def render():
    theme.hero(
        "부동산 AI 주요뉴스",
        "2026-07-29 10:32 KST 기준 · AI, 부동산AI, 프롭티어, 프롭테크 · "
        "AI 기술과 부동산 비즈니스 관점으로 선별한 데일리 인텔리전스",
        side_label="Signal briefing", side_value="1,375 signals", side_note="최근 12시간 · 관련도 98%",
    )

    theme.metric_row(METRICS)

    st.markdown('<div class="exec-eyebrow">EXECUTIVE BRIEF</div><h2 class="brief-h">오늘의 핵심 브리핑</h2>', unsafe_allow_html=True)
    lead_col, side_col = st.columns([1.65, 0.75])
    lead_col.markdown(f"""
    <div class="brief-lead">
      <span class="brief-tag">01 · TOP SIGNAL</span>
      <a href="{NEWS[0]['url']}" target="_blank">{NEWS[0]['title']}</a>
      <p>{NEWS[0]['desc'][0]}</p>
      <div class="brief-why"><b>Why it matters</b><span>{NEWS[0]['decision'][0]}</span></div>
    </div>
    """, unsafe_allow_html=True)
    side_col.markdown("""
    <div class="brief-stat">
      <span class="brief-tag">02 · ISSUE PULSE</span>
      <strong>AX</strong><em>18건에서 포착</em>
      <p>상위 뉴스에서 가장 반복적으로 나타난 세부 키워드</p>
    </div>
    <div class="brief-stat action">
      <span class="brief-tag">03 · ACTION RADAR</span>
      <strong>신규 도입</strong><em>12건</em>
      <p>서비스 벤치마킹과 고객 반응 확인 · LH 언급이 가장 많음</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="range-note">
    \U0001F4E1 <b>API 실제 제공 범위</b> 2025-08-13 13:40 ~ 10:31
    &nbsp;|&nbsp; \U0001F3AF <b>분석 구간</b> 07-28 22:32 ~ 07-29 10:32 (KST)
    &nbsp;|&nbsp; \U0001F50E <b>AI</b> 979건 · <b>부동산AI</b> 997건 · <b>프롭티어</b> 997건
    </div>
    """, unsafe_allow_html=True)

    st.caption("\U0001F552 시간대별 관련 기사 분포 (관련 1,375건)")
    st.bar_chart({"기사 수": {h: c for h, c in HOURLY}}, height=160)

    st.markdown(f'<h2 class="sec">오늘 꼭 봐야 할 뉴스 {len(NEWS)}건</h2>', unsafe_allow_html=True)
    st.markdown('<div class="sec-note">제목과 핵심 요약을 먼저 훑고, 필요한 기사만 원문으로 확인하세요.</div>', unsafe_allow_html=True)

    category_labels = [f"📋 전체 ({len(NEWS)})"] + [
        f"{name} ({sum(1 for n in NEWS if name in n['categories'])})" for name in CATEGORY_NAMES
    ]
    tabs = st.tabs(category_labels)

    with tabs[0]:
        for i, item in enumerate(NEWS, start=1):
            top_class = f"top{i}" if i <= 3 else ""
            theme.news_card(item, item["medal"], top_class)

    for name, tab in zip(CATEGORY_NAMES, tabs[1:]):
        with tab:
            matched = [n for n in NEWS if name in n["categories"]]
            if not matched:
                st.info("이 분류에 해당하는 기사가 없습니다.")
            for i, item in enumerate(matched, start=1):
                theme.news_card(item, str(i))

    theme.footer("네이버 뉴스 검색 API 기반 자동 생성 페이지 (샘플)")
