from datetime import date

import pandas as pd
import streamlit as st

import db
import news_feed
import theme


def _render_news_list(title: str, items: list) -> None:
    st.markdown(f"#### {title}")
    if not items:
        st.caption("해당 소식 없음")
        return
    for it in items:
        st.markdown(f"- [{it['title']}]({it['url']}) · {it['brand']} · {it['posted_at']}")
        if it.get("desc"):
            st.caption(it["desc"])


def _render_sections(date_str: str, content: dict) -> None:
    st.markdown(f"### {date_str}")
    st.caption(f"총 {content['total_count']:,}건 수집")

    st.markdown("#### 📡 채널별 수집 현황")
    counts = sorted(content["channel_counts"].items(), key=lambda kv: -kv[1])
    if counts:
        counts_df = pd.DataFrame([{"채널": ch, "건수": n} for ch, n in counts])
        st.dataframe(counts_df, use_container_width=True, hide_index=True)
    else:
        st.caption("수집된 데이터 없음")

    st.markdown("#### 📰 채널별 주요 뉴스")
    for ch, items in content["channel_top_news"].items():
        with st.expander(f"{ch} ({len(items)}건)"):
            for it in items:
                st.markdown(f"- [{it['title']}]({it['url']}) · {it['brand']} · {it['posted_at']}")

    _render_news_list("🏠 프롭티어 관련 뉴스", content["own_brand_news"])
    _render_news_list("⚔️ 경쟁사 동향", content["competitor_news"])
    _render_news_list("🌐 시장 동향", content["market_news"])


def render():
    archived_dates = sorted(db.get_archived_briefing_dates(), reverse=True)
    today_str = date.today().strftime("%Y-%m-%d")

    # 오늘의 미리보기는 내일 확정될 아카이브와 정확히 같은 기준(채널 노출 설정 무관,
    # 건수 제한 없음)으로 계산해야 한다 — cached_db.get_mentions(limit=BROAD_LIMIT)를
    # 쓰면 1000건 넘는 날 미리보기와 실제 확정본의 총 건수가 달라져 보인다.
    today_mentions = db.get_mentions_by_collected_date(today_str)
    has_today = bool(today_mentions)

    # 확정된 날짜 + "데이터는 있지만 아직 확정 안 된" 과거 날짜(오늘 제외)를 합쳐서
    # 목록에 노출한다 — 배포 직후 첫 스케줄러 tick 전이거나 스케줄러 스레드가 죽은
    # 경우에도 그 날짜가 목록에서 아예 사라지지 않게 한다.
    unarchived_with_data = db.get_distinct_mention_dates() - set(archived_dates) - {today_str}
    other_dates = sorted(set(archived_dates) | unarchived_with_data, reverse=True)
    dates = ([today_str] if has_today else []) + [d for d in other_dates if d != today_str]

    if not dates:
        theme.hero("\U0001F4DD 브리핑 아카이브", "아직 수집된 데이터가 없습니다")
        st.info("설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    theme.hero(
        "\U0001F4DD 브리핑 아카이브",
        f"확정된 브리핑 {len(archived_dates):,}건 · 왼쪽 목록에서 날짜를 고르세요",
    )

    if "briefing_date_idx" not in st.session_state or st.session_state.briefing_date_idx >= len(dates):
        st.session_state.briefing_date_idx = 0

    list_col, panel_col = st.columns([1, 2.4])

    with list_col:
        for i, d in enumerate(dates):
            selected = i == st.session_state.briefing_date_idx
            prefix = "\U0001F449 " if selected else ""
            label = f"{d} (진행중)" if d == today_str and has_today else d
            if st.button(f"{prefix}{label}", key=f"bf_{i}", use_container_width=True):
                st.session_state.briefing_date_idx = i
                st.rerun()

    with panel_col:
        picked_date = dates[st.session_state.briefing_date_idx]
        if picked_date == today_str and has_today:
            st.info("\U0001F504 오늘은 아직 진행 중입니다 — 자정이 지나면 자동으로 확정됩니다.")
            content = news_feed.build_briefing_archive_content(
                today_mentions, news_feed.own_brand_names(),
                news_feed.competitor_brand_names(), news_feed.market_brand_names(),
            )
            _render_sections(today_str, content)
        else:
            archive = db.get_briefing_archive(picked_date)
            if archive is None:
                st.info("⏳ 아직 확정 전입니다 — 스케줄러가 곧 처리합니다.")
            else:
                _render_sections(archive["date"], archive)

    theme.footer("확정된 날짜는 고정 기록 · 오늘은 실시간 집계")
