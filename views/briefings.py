import streamlit as st

import cached_db
import news_feed
import theme


def render():
    mentions = cached_db.get_mentions(limit=news_feed.BROAD_LIMIT, channels=tuple(news_feed.enabled_channels()))

    if not mentions:
        theme.hero("\U0001F4DD 브리핑 아카이브", "아직 수집된 데이터가 없습니다")
        st.info("설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    briefings = news_feed.build_briefings(mentions, news_feed.own_brand_names())

    theme.hero(
        "\U0001F4DD 브리핑 아카이브",
        f"수집일 기준 브리핑 {len(briefings):,}건 · 왼쪽 목록에서 날짜를 고르세요",
    )

    if "briefing_idx" not in st.session_state or st.session_state.briefing_idx >= len(briefings):
        st.session_state.briefing_idx = 0

    list_col, panel_col = st.columns([1, 2.4])

    with list_col:
        for i, b in enumerate(briefings):
            selected = i == st.session_state.briefing_idx
            prefix = "\U0001F449 " if selected else ""
            if st.button(f"{prefix}{b['date']}", key=f"bf_{i}", use_container_width=True):
                st.session_state.briefing_idx = i
                st.rerun()

    with panel_col:
        b = briefings[st.session_state.briefing_idx]
        st.markdown(f"""
        <div class="sl-item top1">
          <div class="sl-signal">{b['date']}</div>
          <div class="sl-head"><span class="sl-title">{b['title']}</span></div>
          <div class="insight"><div class="insight-title">브리핑 요약</div>
            <ul><li>{b['summary']}</li></ul></div>
          <div class="sl-meta">해당 날짜에 수집된 mentions를 자동 요약했습니다.</div>
        </div>
        """, unsafe_allow_html=True)

    theme.footer("실제 수집 데이터(mentions)를 수집일 기준으로 묶어 자동 생성")
