import streamlit as st

import theme
from data import NEWS
from report_pdf import build_deck_html, generate_pdf_bytes


def render():
    theme.hero(
        "\U0001F4C4 PDF 보고서",
        "오늘의 브리핑을 카드뉴스 형태의 인쇄용 PDF로 내보냅니다 · 아래 미리보기와 동일한 구성으로 다운로드됩니다",
    )

    top5 = NEWS[:5]

    col_dl, col_note = st.columns([1, 3])
    with col_dl:
        if st.button("\U0001F4E5 PDF 생성", type="primary", use_container_width=True):
            with st.spinner("PDF 생성 중... (Chromium 렌더링, 수 초 소요)"):
                try:
                    st.session_state["report_pdf_bytes"] = generate_pdf_bytes(top5)
                except Exception as e:
                    st.session_state["report_pdf_bytes"] = None
                    st.error(f"PDF 생성 실패: {e}")
    with col_note:
        if st.session_state.get("report_pdf_bytes"):
            st.download_button(
                "\U0001F4BE report.pdf 저장", data=st.session_state["report_pdf_bytes"],
                file_name="report.pdf", mime="application/pdf", use_container_width=True,
            )
        else:
            st.caption("먼저 'PDF 생성'을 눌러 아래 미리보기와 동일한 카드뉴스 PDF를 만드세요.")

    st.markdown('<h2 class="sec">미리보기</h2>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-note">표지 1장 + 랭킹 1~5위 카드 — 실제 다운로드되는 PDF와 완전히 동일한 레이아웃입니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="zoom:0.85; transform-origin: top left;">{build_deck_html(top5)}</div>',
        unsafe_allow_html=True,
    )

    theme.footer("PDF 보고서 · 카드뉴스 6장 구성")
