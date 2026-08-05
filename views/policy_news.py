from datetime import datetime

import streamlit as st

import db
import policy_feed
import theme

_SOURCES = ["국토교통부", "한국부동산원", "LH", "서울시", "HF", "HUG", "SH"]


def render():
    now = datetime.now()
    events = db.get_policy_events(limit=2000)

    if not events:
        theme.hero(
            "\U0001F3DB️ 정부 정책 뉴스",
            f"{now.strftime('%Y-%m-%d %H:%M')} KST 기준 · 아직 수집된 정책 데이터가 없습니다",
        )
        st.info("설정 → 데이터 수집 → 정부 정책에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    total_count = db.count_policy_events()
    recent_count = sum(1 for e in events if policy_feed._is_recent(e, now))
    source_counts = {}
    for e in events:
        source_counts[e["source"]] = source_counts.get(e["source"], 0) + 1
    top_source, top_source_count = policy_feed.build_source_pulse(events)
    pulse_cat, pulse_count = policy_feed.build_policy_pulse(events)

    items = policy_feed.build_policy_items(events, now)
    daily = policy_feed.build_daily(events, now)
    top = items[0]

    theme.hero(
        "\U0001F3DB️ 정부 정책 뉴스",
        f"{now.strftime('%Y-%m-%d %H:%M')} KST 기준 · 국토교통부·한국부동산원·LH·서울시·HF·HUG·SH "
        "7개 기관 보도자료 · AI·부동산 정책 임팩트 관점으로 선별한 인텔리전스",
        side_label="Policy briefing", side_value=f"{len(events):,} releases",
        side_note=f"최근 {policy_feed.RECENCY_DAYS}일 · {recent_count:,}건",
    )

    theme.metric_row([
        {"icon": "◫", "value": f"{total_count:,}", "label": "전체 수집"},
        {"icon": "◷", "value": f"{recent_count:,}", "label": f"최근 {policy_feed.RECENCY_DAYS}일"},
        {"icon": "\U0001F3DB", "value": f"{len(source_counts)}", "label": "수집 기관 수"},
        {"icon": "★", "value": top_source, "label": "최다 발표 기관"},
    ])

    st.markdown('<div class="exec-eyebrow">EXECUTIVE BRIEF</div><h2 class="brief-h">정책 핵심 브리핑</h2>', unsafe_allow_html=True)
    lead_col, side_col = st.columns([1.65, 0.75])
    lead_col.markdown(f"""
    <div class="brief-lead">
      <span class="brief-tag">01 · TOP RELEASE</span>
      <a href="{top['url']}" target="_blank">{top['title']}</a>
      <p>{top['source']} · {top['department']} · 조회 {top['view_count']:,}회</p>
      <div class="brief-why"><b>Why it matters</b><span>최근 발표 중 신호 점수·조회수가 가장 높은 보도자료입니다.</span></div>
    </div>
    """, unsafe_allow_html=True)
    side_col.markdown(f"""
    <div class="brief-stat">
      <span class="brief-tag">02 · POLICY PULSE</span>
      <strong>{pulse_cat}</strong><em>{pulse_count:,}건에서 포착</em>
      <p>최근 발표에서 가장 반복적으로 나타난 정책 유형</p>
    </div>
    <div class="brief-stat action">
      <span class="brief-tag">03 · SOURCE RADAR</span>
      <strong>{top_source}</strong><em>{top_source_count:,}건</em>
      <p>가장 활발하게 보도자료를 발표한 기관</p>
    </div>
    """, unsafe_allow_html=True)

    st.caption(f"\U0001F552 최근 {len(daily)}일 발표 추이")
    theme.bar_chart({d: c for d, c in daily}, height=160)

    title_col, help_col = st.columns([10, 1], vertical_alignment="center")
    title_col.markdown('<h2 class="sec">기관별 보도자료</h2>', unsafe_allow_html=True)
    with help_col:
        with st.popover("❓"):
            st.markdown(policy_feed.category_legend_markdown())

    source_pick = st.selectbox("기관 필터", ["전체"] + _SOURCES)
    filtered_events = events if source_pick == "전체" else [e for e in events if e["source"] == source_pick]
    display_items = policy_feed.build_policy_items(filtered_events, now)[:policy_feed.DISPLAY_LIMIT]

    st.caption(f"조회 결과 {len(display_items):,}건")

    category_labels = [f"📋 전체 ({len(display_items):,})"] + [
        f"{name} ({sum(1 for it in display_items if name in it['categories']):,})"
        for name in policy_feed.POLICY_CATEGORY_ORDER
    ]
    tabs = st.tabs(category_labels)

    with tabs[0]:
        if not display_items:
            st.info("조건에 맞는 보도자료가 없습니다.")
        for i, item in enumerate(display_items, start=1):
            top_class = f"top{i}" if i <= 3 else ""
            theme.policy_signal_card(item, item["medal"], top_class)

    for name, tab in zip(policy_feed.POLICY_CATEGORY_ORDER, tabs[1:]):
        with tab:
            matched = [it for it in display_items if name in it["categories"]]
            if not matched:
                st.info("이 분류에 해당하는 보도자료가 없습니다.")
            for i, item in enumerate(matched, start=1):
                theme.policy_signal_card(item, str(i))

    theme.footer("실제 수집 데이터(policy_events) 기반 · 카테고리/점수는 키워드 휴리스틱으로 계산")
