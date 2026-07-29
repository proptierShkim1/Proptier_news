import streamlit as st

import theme
from data import NEWS


def render():
    theme.hero(
        "\U0001F4C4 PDF 보고서",
        "오늘의 브리핑을 인쇄용 PDF로 내보냅니다 · 원본 사이트는 /report.pdf 정적 파일로 제공",
    )

    st.info(
        "이 화면은 레이아웃 구성만 재현한 샘플입니다. 실제 PDF 생성 파이프라인(예: WeasyPrint·Playwright)은 "
        "연결되어 있지 않아 다운로드 버튼은 동작하지 않습니다.",
        icon="\U0001F4C4",
    )
    st.button("\U0001F4E5 PDF 다운로드 (샘플 · 비활성)", disabled=True)

    st.markdown('<h2 class="sec">보고서 미리보기</h2>', unsafe_allow_html=True)
    st.markdown('<div class="sec-note">PDF에는 아래 상위 랭킹 뉴스가 요약 형태로 인쇄됩니다.</div>', unsafe_allow_html=True)

    for i, item in enumerate(NEWS, start=1):
        top_class = f"top{i}" if i <= 3 else ""
        theme.news_card(item, item["medal"] if i <= 3 else str(i), top_class)

    theme.footer("PDF 보고서 미리보기 (샘플)")
