from datetime import datetime, timedelta

import streamlit as st

import theme
from data import FIRMS, ISSUES, TODAY

_PERIOD_DAYS = {"누적 전체": None, "최근 1년": 365, "최근 1개월": 30, "최근 1주": 7}


def _issue_date(iss):
    return datetime.strptime(iss["date"], "%Y-%m-%d").date()


def render():
    theme.hero(
        "\U0001F3E2 부동산사별 이슈 동향",
        f"기준 {TODAY.isoformat()} 10:36 (KST) · {len(FIRMS)}개 부동산사 · 이슈 {len(ISSUES)}건 (샘플) · news.db 자동 누적 구조를 재현한 화면",
    )

    period = st.segmented_control(
        "\U0001F5D3️ 이슈 기간", list(_PERIOD_DAYS.keys()),
        default="누적 전체", label_visibility="collapsed",
    )
    period = period or "누적 전체"

    firm_pick = st.selectbox("\U0001F3E2 부동산사 필터", ["전체"] + FIRMS)

    days = _PERIOD_DAYS[period]
    filtered = ISSUES
    if days is not None:
        cutoff = TODAY - timedelta(days=days)
        filtered = [iss for iss in filtered if _issue_date(iss) >= cutoff]
    if firm_pick != "전체":
        filtered = [iss for iss in filtered if iss.get("firm") == firm_pick]

    st.caption(f"현재 필터: {period} · {firm_pick} · 이슈 {len(filtered)}건 / 전체 {len(ISSUES)}건")

    st.markdown('<h2 class="sec">\U0001F5C2️ 이슈 타임라인</h2>', unsafe_allow_html=True)
    monthly = {}
    for iss in filtered:
        key = _issue_date(iss).strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + 1
    if monthly:
        st.bar_chart({"이슈 건수": dict(sorted(monthly.items()))}, height=160)
    else:
        st.caption("해당 조건에 표시할 타임라인 데이터가 없습니다.")

    st.markdown(f'<h2 class="sec">\U0001F4F0 이슈 이력 ({len(filtered)}건)</h2>', unsafe_allow_html=True)
    if not filtered:
        st.info("조건에 맞는 이슈가 없습니다.")
    for iss in filtered:
        badge = f'<span class="iss-live">진행중</span>' if iss["live"] else f'<span class="iss-done">{iss["date"][5:]}</span>'
        articles_html = "".join(
            f'<li><span class="tl-meta">{d}</span><a href="{u}" target="_blank">{t}</a></li>'
            for d, t, u in iss["articles"]
        )
        st.markdown(f"""
        <details class="iss">
          <summary>
            <span class="iss-cat" style="background:{iss['cat_bg']};color:{iss['cat_fg']}">{iss['cat']}</span>
            <span class="iss-title">{iss['title']}</span>
            <span class="iss-meta">{iss.get('firm', '')} · 기사 {iss['count']}건 · {iss['date']}</span>{badge}
          </summary>
          <ul class="iss-arts">{articles_html}</ul>
        </details>
        """, unsafe_allow_html=True)

    theme.footer("부동산사별 이슈 동향 (샘플 데이터)")
