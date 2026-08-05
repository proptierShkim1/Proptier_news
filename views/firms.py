from datetime import datetime, timedelta

import streamlit as st

import db
import news_feed
import theme

_PERIOD_DAYS = {"누적 전체": None, "최근 1년": 365, "최근 1개월": 30, "최근 1주": 7}


def _issue_date(iss):
    return datetime.strptime(iss["date"], "%Y-%m-%d").date()


def render():
    now = datetime.now()
    today = now.date()
    mentions = db.get_mentions(limit=news_feed.BROAD_LIMIT, channels=news_feed.enabled_channels())

    if not mentions:
        theme.hero("\U0001F3E2 부동산사별 이슈 동향", f"기준 {today.isoformat()} · 아직 수집된 데이터가 없습니다")
        st.info("설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    issues = news_feed.build_issues(mentions, now)
    firms = sorted({iss["firm"] for iss in issues if iss["firm"]})

    theme.hero(
        "\U0001F3E2 부동산사별 이슈 동향",
        f"기준 {now.strftime('%Y-%m-%d %H:%M')} (KST) · {len(firms):,}개 부동산사 · 이슈 {len(issues):,}건 · "
        "실제 수집(mentions) 데이터를 건별 이슈 카드로 표시",
    )

    period = st.segmented_control(
        "\U0001F5D3️ 이슈 기간", list(_PERIOD_DAYS.keys()),
        default="누적 전체", label_visibility="collapsed",
    )
    period = period or "누적 전체"

    firm_pick = st.selectbox("\U0001F3E2 부동산사 필터", ["전체"] + firms)

    days = _PERIOD_DAYS[period]
    filtered = issues
    if days is not None:
        cutoff = today - timedelta(days=days)
        filtered = [iss for iss in filtered if _issue_date(iss) >= cutoff]
    if firm_pick != "전체":
        filtered = [iss for iss in filtered if iss.get("firm") == firm_pick]

    st.caption(f"현재 필터: {period} · {firm_pick} · 이슈 {len(filtered):,}건 / 전체 {len(issues):,}건")

    st.markdown('<h2 class="sec">\U0001F5C2️ 이슈 타임라인</h2>', unsafe_allow_html=True)
    monthly = {}
    for iss in filtered:
        key = _issue_date(iss).strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + 1
    if monthly:
        st.bar_chart({"이슈 건수": dict(sorted(monthly.items()))}, height=160)
    else:
        st.caption("해당 조건에 표시할 타임라인 데이터가 없습니다.")

    title_col, help_col = st.columns([10, 1], vertical_alignment="center")
    title_col.markdown(f'<h2 class="sec">\U0001F4F0 이슈 이력 ({len(filtered):,}건)</h2>', unsafe_allow_html=True)
    with help_col:
        with st.popover("❓"):
            st.markdown(news_feed.category_legend_markdown())
    if not filtered:
        st.info("조건에 맞는 이슈가 없습니다.")
    for iss in filtered[:news_feed.DISPLAY_LIMIT]:
        badge = '<span class="iss-live">진행중</span>' if iss["live"] else f'<span class="iss-done">{iss["date"][5:]}</span>'
        articles_html = "".join(
            f'<li><span class="tl-meta">{d}</span><a href="{u}" target="_blank">{t}</a></li>'
            for d, t, u in iss["articles"]
        )
        st.markdown(f"""
        <details class="iss">
          <summary>
            <span class="iss-cat" style="background:{iss['cat_bg']};color:{iss['cat_fg']}">{iss['cat']}</span>
            <span class="iss-title">{iss['title']}</span>
            <span class="iss-meta">{iss.get('firm', '')} · 기사 {iss['count']:,}건 · {iss['date']}</span>{badge}
          </summary>
          <ul class="iss-arts">{articles_html}</ul>
        </details>
        """, unsafe_allow_html=True)

    theme.footer("실제 수집 데이터(mentions) 기반 · 이슈는 건별 카드(사건 클러스터링 없음)")
