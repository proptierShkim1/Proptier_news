import streamlit as st

import theme
from data import BRIEFINGS


def render():
    theme.hero(
        "\U0001F4DD 브리핑 아카이브",
        f"아침 브리핑 {len(BRIEFINGS)}건 · 샘플 {len(BRIEFINGS)}일치 · 왼쪽 목록에서 날짜를 고르세요",
    )

    if "briefing_idx" not in st.session_state:
        st.session_state.briefing_idx = 0

    list_col, panel_col = st.columns([1, 2.4])

    with list_col:
        for i, b in enumerate(BRIEFINGS):
            selected = i == st.session_state.briefing_idx
            prefix = "\U0001F449 " if selected else ""
            if st.button(f"{prefix}{b['date']}", key=f"bf_{i}", use_container_width=True):
                st.session_state.briefing_idx = i
                st.rerun()

    with panel_col:
        b = BRIEFINGS[st.session_state.briefing_idx]
        st.markdown(f"""
        <div class="sl-item top1">
          <div class="sl-signal">{b['date']}</div>
          <div class="sl-head"><span class="sl-title">{b['title']}</span></div>
          <div class="insight"><div class="insight-title">브리핑 요약</div>
            <ul><li>{b['summary']}</li></ul></div>
          <div class="sl-meta">해당 날짜 브리핑 markdown 파일 전문이 이 자리에 표시됩니다 (샘플 데이터).</div>
        </div>
        """, unsafe_allow_html=True)

    theme.footer("브리핑 폴더의 Markdown 파일을 자동 수록 (샘플)")
