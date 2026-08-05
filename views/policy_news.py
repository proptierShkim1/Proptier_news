from datetime import datetime, timedelta

import streamlit as st

import db
import theme

_SOURCES = ["국토교통부", "한국부동산원", "LH", "서울시", "HF", "HUG", "SH"]
_RECENT_DAYS = 7
_DISPLAY_LIMIT = 30


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
    recent_cutoff = (now - timedelta(days=_RECENT_DAYS)).strftime("%Y-%m-%d")
    recent_count = sum(1 for e in events if (e.get("announced_at") or "") >= recent_cutoff)
    source_counts = {}
    for e in events:
        source_counts[e["source"]] = source_counts.get(e["source"], 0) + 1
    top_source = max(source_counts.items(), key=lambda kv: kv[1])[0] if source_counts else "-"

    theme.hero(
        "\U0001F3DB️ 정부 정책 뉴스",
        f"{now.strftime('%Y-%m-%d %H:%M')} KST 기준 · 국토교통부·한국부동산원·LH·서울시·HF·HUG·SH "
        "7개 기관 보도자료",
    )

    theme.metric_row([
        {"icon": "◫", "value": f"{total_count:,}", "label": "전체 수집"},
        {"icon": "◷", "value": f"{recent_count:,}", "label": f"최근 {_RECENT_DAYS}일"},
        {"icon": "\U0001F3DB", "value": f"{len(source_counts)}", "label": "수집 기관 수"},
        {"icon": "★", "value": top_source, "label": "최다 발표 기관"},
    ])

    st.markdown('<h2 class="sec">기관별 보도자료</h2>', unsafe_allow_html=True)
    source_pick = st.selectbox("기관 필터", ["전체"] + _SOURCES)
    filtered = events if source_pick == "전체" else [e for e in events if e["source"] == source_pick]
    filtered = sorted(filtered, key=lambda e: e.get("announced_at") or "", reverse=True)

    st.caption(f"조회 결과 {len(filtered):,}건")
    if not filtered:
        st.info("조건에 맞는 보도자료가 없습니다.")
    for e in filtered[:_DISPLAY_LIMIT]:
        theme.policy_card(e)

    theme.footer("실제 수집 데이터(policy_events) 기반")
