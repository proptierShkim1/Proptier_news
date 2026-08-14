from datetime import date

import streamlit as st

import db
import news_feed
import theme
from utils import escape_html

_MEDALS = ["🥇", "🥈", "🥉"]


def _rank(i: int) -> str:
    return _MEDALS[i] if i < 3 else str(i + 1)


def _archive_card_html(item: dict, rank: str) -> str:
    desc_html = (
        f'<ul class="sl-desc"><li>{escape_html(item["desc"])}</li></ul>' if item.get("desc") else ""
    )
    meta = " · ".join(escape_html(v) for v in (item.get("brand"), item.get("channel"), item.get("posted_at")) if v)
    return f"""
    <div class="sl-item">
      <div class="sl-signal">{escape_html(item.get('signal', ''))}</div>
      <div class="sl-head"><span class="sl-rank">{rank}</span>
        <a class="sl-title" href="{escape_html(item['url'])}" target="_blank">{escape_html(item['title'])}</a></div>
      {desc_html}
      <div class="sl-meta">{meta}</div>
    </div>
    """


def _render_news_list(title: str, note: str, items: list) -> None:
    st.markdown(f'<h2 class="sec">{title}</h2>', unsafe_allow_html=True)
    st.markdown(f'<div class="sec-note">{note}</div>', unsafe_allow_html=True)
    if not items:
        st.caption("해당 소식 없음")
        return
    for i, it in enumerate(items):
        st.markdown(_archive_card_html(it, _rank(i)), unsafe_allow_html=True)


def _render_channel_counts(date_str: str, total_count: int, counts: dict) -> None:
    st.markdown(f'<h2 class="sec">채널별 수집 현황 ({date_str})</h2>', unsafe_allow_html=True)
    st.markdown('<div class="sec-note">그날 채널별로 몇 건씩 수집됐는지 보여줍니다.</div>', unsafe_allow_html=True)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    # "전체"를 별도의 큰 타일로 떼어놓지 않고 같은 그리드의 첫 칸으로 넣어서, 위아래로
    # 타일 크기가 안 맞아 보이는 문제 없이 전부 같은 크기로 나오게 한다.
    metrics = [{"icon": "🗞️", "value": f"{total_count:,}", "label": "전체"}] + [
        {"icon": "📡", "value": f"{n:,}", "label": ch} for ch, n in ranked
    ]
    # 이 화면의 지표 타일은 좁은 오른쪽 패널(전체 폭의 약 70%) 안에 들어가므로, 채널이
    # 많을 때(5~6개) 한 줄에 다 넣으면 타일이 밀려 좁아진다 — 한 줄에 최대 3개로 줄바꿈.
    # theme.metric_row(chunk)를 그대로 쓰면 마지막 줄(예: 3,3,1일 때 1개)의 컬럼 폭이
    # st.columns(len(chunk))로 매번 다시 계산돼 앞줄의 3등분 타일보다 넓어져 크기가 안
    # 맞아 보인다 — 항상 고정으로 3칸을 만들고 남는 칸은 비워둬서 모든 타일 크기를
    # 동일하게 유지한다.
    row_size = 3
    for i in range(0, len(metrics), row_size):
        row = metrics[i:i + row_size]
        cols = st.columns(row_size)
        for col, m in zip(cols, row):
            col.markdown(f"""
            <div class="metric-box"><span class="mi">{m['icon']}</span>
            <div class="v">{m['value']}</div><div class="l">{m['label']}</div></div>
            """, unsafe_allow_html=True)


def _render_channel_top_news(channel_top_news: dict) -> None:
    st.markdown('<h2 class="sec">채널별 주요 뉴스</h2>', unsafe_allow_html=True)
    st.markdown('<div class="sec-note">채널별로 가장 점수가 높은 기사를 모았습니다.</div>', unsafe_allow_html=True)
    if not channel_top_news:
        st.caption("수집된 데이터 없음")
        return
    channels = list(channel_top_news.keys())
    tabs = st.tabs(channels)
    for ch, tab in zip(channels, tabs):
        with tab:
            items = channel_top_news[ch]
            if not items:
                st.caption("해당 소식 없음")
                continue
            for i, it in enumerate(items):
                st.markdown(_archive_card_html(it, _rank(i)), unsafe_allow_html=True)


def _render_sections(date_str: str, content: dict) -> None:
    _render_channel_counts(date_str, content["total_count"], content["channel_counts"])
    _render_channel_top_news(content["channel_top_news"])
    _render_news_list("🏠 프롭티어 관련 뉴스", "자사 관련 소식만 모았습니다.", content["own_brand_news"])
    _render_news_list("⚔️ 경쟁사 동향", "경쟁사 관련 소식만 모았습니다.", content["competitor_news"])
    _render_news_list("🌐 시장 동향", "AI·프롭테크 등 시장 전반의 소식입니다.", content["market_news"])


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
