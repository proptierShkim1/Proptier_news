import streamlit as st

import db
import news_feed
import summarizer
import theme
from report_pdf import build_deck_html, generate_pdf_bytes


def _ensure_pdf_summaries(items: list[dict]) -> None:
    """PDF에 실제로 나오는 상위 항목(top5)에 대해서만 AI 요약을 만든다 — 전체 수집
    기사를 대상으로 하면 대부분 PDF에 나오지도 않을 항목까지 호출하는 낭비가 생긴다.
    원문(content)이 있고 아직 summary가 비어있는 항목만 호출하고, 결과는 DB에 저장해
    다음 번 렌더링부터는 다시 호출하지 않는다."""
    for item in items:
        if item.get("content") and not item.get("summary") and item.get("mention_id"):
            ai_summary = summarizer.summarize_article(item["title"], item["content"])
            if ai_summary:
                db.update_mention_summary(item["mention_id"], ai_summary)
                item["summary"] = ai_summary
                item["desc_long"] = [ai_summary]


def render():
    theme.hero(
        "\U0001F4C4 PDF 보고서",
        "오늘의 브리핑을 카드뉴스 형태의 인쇄용 PDF로 내보냅니다 · 아래 미리보기와 동일한 구성으로 다운로드됩니다",
    )

    mentions = db.get_mentions(limit=news_feed.RECENT_LIMIT, channels=news_feed.enabled_channels())
    if not mentions:
        st.info("아직 수집된 데이터가 없습니다. 설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    news_items = news_feed.build_news_items(mentions, news_feed.own_brand_names())
    top5 = news_items[:5]
    _ensure_pdf_summaries(top5)
    total_count = db.count_mentions()
    ai_count = sum(1 for it in news_items if "AI" in it["categories"])

    col_dl, col_note = st.columns([1, 3])
    with col_dl:
        if st.button("\U0001F4E5 PDF 생성", type="primary", use_container_width=True):
            with st.spinner("PDF 생성 중... (Chromium 렌더링, 수 초 소요)"):
                try:
                    st.session_state["report_pdf_bytes"] = generate_pdf_bytes(top5, total_count, ai_count)
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
        f'<div style="zoom:0.85; transform-origin: top left;">{build_deck_html(top5, total_count, ai_count)}</div>',
        unsafe_allow_html=True,
    )

    theme.footer("PDF 보고서 · 카드뉴스 6장 구성")
