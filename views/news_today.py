from datetime import datetime

import streamlit as st

import theme
import db
import news_feed
from utils import load_keywords


def render():
    now = datetime.now()
    mentions = db.get_mentions(limit=news_feed.RECENT_LIMIT, channels=news_feed.enabled_channels())

    if not mentions:
        theme.hero(
            "부동산 AI 주요뉴스",
            f"{now.strftime('%Y-%m-%d %H:%M')} KST 기준 · 아직 수집된 데이터가 없습니다",
        )
        st.info("설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    total_count = db.count_mentions()
    own_brands = {b["name"] for b in load_keywords().get("brands", []) if b.get("role") == "own"}

    news_items = news_feed.build_news_items(mentions, own_brands, now)
    metrics = news_feed.build_metrics(mentions, total_count, now)
    hourly = news_feed.build_hourly(mentions, now)
    issue_cat, issue_count = news_feed.build_issue_pulse(mentions)
    action_count, action_brand = news_feed.build_action_radar(mentions)
    top = news_items[0]

    theme.hero(
        "부동산 AI 주요뉴스",
        f"{now.strftime('%Y-%m-%d %H:%M')} KST 기준 · 최근 수집 {len(mentions):,}건 분석 · "
        "AI 기술과 부동산 비즈니스 관점으로 선별한 데일리 인텔리전스",
        side_label="Signal briefing", side_value=f"{len(mentions):,} signals",
        side_note=f"최근 {news_feed.RECENCY_HOURS}시간 · {metrics[1]['value']}건",
    )

    theme.metric_row(metrics)

    st.markdown('<div class="exec-eyebrow">EXECUTIVE BRIEF</div><h2 class="brief-h">오늘의 핵심 브리핑</h2>', unsafe_allow_html=True)
    lead_col, side_col = st.columns([1.65, 0.75])
    lead_col.markdown(f"""
    <div class="brief-lead">
      <span class="brief-tag">01 · TOP SIGNAL</span>
      <a href="{top['url']}" target="_blank">{top['title']}</a>
      <p>{top['desc'][0] if top['desc'] else '(요약 없음)'}</p>
      <div class="brief-why"><b>Why it matters</b><span>{top['decision'][0]}</span></div>
    </div>
    """, unsafe_allow_html=True)
    side_col.markdown(f"""
    <div class="brief-stat">
      <span class="brief-tag">02 · ISSUE PULSE</span>
      <strong>{issue_cat}</strong><em>{issue_count:,}건에서 포착</em>
      <p>상위 뉴스에서 가장 반복적으로 나타난 세부 키워드</p>
    </div>
    <div class="brief-stat action">
      <span class="brief-tag">03 · ACTION RADAR</span>
      <strong>신규 도입</strong><em>{action_count:,}건</em>
      <p>서비스 벤치마킹과 고객 반응 확인 · {(action_brand + ' 언급이 가장 많음') if action_brand else '관련 브랜드 없음'}</p>
    </div>
    """, unsafe_allow_html=True)

    oldest = min(m["collected_at"] for m in mentions)
    newest = max(m["collected_at"] for m in mentions)
    st.markdown(f"""
    <div class="range-note">
    \U0001F4E1 <b>분석 대상</b> 최근 수집 {len(mentions):,}건
    &nbsp;|&nbsp; \U0001F3AF <b>분석 구간</b> {oldest} ~ {newest}
    </div>
    """, unsafe_allow_html=True)

    st.caption(f"\U0001F552 최근 {news_feed.RECENCY_HOURS}시간 시간대별 수집 분포")
    st.bar_chart({"기사 수": {h: c for h, c in hourly}}, height=160)

    display_items = news_items[:news_feed.DISPLAY_LIMIT]
    title_col, help_col = st.columns([10, 1], vertical_alignment="center")
    title_col.markdown(f'<h2 class="sec">오늘 꼭 봐야 할 뉴스 {len(display_items):,}건</h2>', unsafe_allow_html=True)
    with help_col:
        with st.popover("❓"):
            st.markdown(news_feed.category_legend_markdown())
    st.markdown('<div class="sec-note">제목과 핵심 요약을 먼저 훑고, 필요한 기사만 원문으로 확인하세요.</div>', unsafe_allow_html=True)

    category_labels = [f"📋 전체 ({len(display_items):,})"] + [
        f"{name} ({sum(1 for n in display_items if name in n['categories']):,})" for name in news_feed.CATEGORY_ORDER
    ]
    tabs = st.tabs(category_labels)

    with tabs[0]:
        for i, item in enumerate(display_items, start=1):
            top_class = f"top{i}" if i <= 3 else ""
            theme.news_card(item, item["medal"], top_class)

    for name, tab in zip(news_feed.CATEGORY_ORDER, tabs[1:]):
        with tab:
            matched = [n for n in display_items if name in n["categories"]]
            if not matched:
                st.info("이 분류에 해당하는 기사가 없습니다.")
            for i, item in enumerate(matched, start=1):
                theme.news_card(item, str(i))

    theme.footer("실제 수집 데이터(mentions) 기반 · 카테고리/점수는 키워드 휴리스틱으로 계산")
