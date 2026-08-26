from datetime import date, datetime

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
    if not items:
        return
    st.markdown(f'<h2 class="sec">{title}</h2>', unsafe_allow_html=True)
    st.markdown(f'<div class="sec-note">{note}</div>', unsafe_allow_html=True)
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
    # 채널이 많을 때(5~6개) 한 줄에 다 넣으면 타일이 밀려 좁아진다 — 한 줄에 최대 4개로 줄바꿈.
    # theme.metric_row(chunk)를 그대로 쓰면 마지막 줄(예: 4,4,1일 때 1개)의 컬럼 폭이
    # st.columns(len(chunk))로 매번 다시 계산돼 앞줄의 4등분 타일보다 넓어져 크기가 안
    # 맞아 보인다 — 항상 고정으로 4칸을 만들고 남는 칸은 비워둬서 모든 타일 크기를
    # 동일하게 유지한다.
    row_size = 4
    for i in range(0, len(metrics), row_size):
        row = metrics[i:i + row_size]
        cols = st.columns(row_size)
        for col, m in zip(cols, row):
            col.markdown(f"""
            <div class="metric-box"><span class="mi">{m['icon']}</span>
            <div class="v">{m['value']}</div><div class="l">{m['label']}</div></div>
            """, unsafe_allow_html=True)


def _ordinal_day(d: date) -> str:
    n = d.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _calendar_label_fragment(d: date) -> str:
    """st.date_input이 그리는 BaseWeb 달력의 각 날짜 셀은 `aria-label`에
    "Choose Wednesday, August 24th 2026. It's available." 형식의 영문 문자열을 담는다
    (선택된 날짜는 "Selected. ...", 범위 밖은 "Not available. ..."로 접두사만 다름).
    "August 24th 2026"처럼 월 이름이 앞에 고정으로 붙는 부분만 뽑아 부분일치 셀렉터로
    쓰면, hashed CSS 클래스명(st-xx)과 달리 Streamlit 버전이 바뀌어도 잘 안 깨진다."""
    return f"{d.strftime('%B')} {_ordinal_day(d)} {d.year}"


def _calendar_marker_rule(dates: set, dot_style: str) -> str:
    selectors = [f'[aria-label*="{_calendar_label_fragment(d)}"]' for d in sorted(dates)]
    if not selectors:
        return ""
    base = ", ".join(selectors)
    # BaseWeb 달력이 선택/오늘 표시에 이미 ::after 의사요소를 자체적으로 쓰고 있어서
    # (선택된 날짜 뒤의 둥근 배경 하이라이트가 바로 그것) 여기서 ::after를 덮어쓰면
    # 그 표시가 우리 점으로 통째로 바뀌어버린다 — 안 쓰는 ::before를 대신 쓴다.
    marker = ", ".join(f"{s}::before" for s in selectors)
    return f"""
    {base} {{ position: relative !important; }}
    {marker} {{
      content:"" !important; position:absolute !important; left:50% !important;
      bottom:4px !important; top:auto !important; transform:translateX(-50%) !important;
      width:5px !important; height:5px !important; border-radius:50% !important;
      {dot_style}
    }}
    """


def _calendar_marker_css(confirmed: set, pending: set) -> str:
    """달력 팝업에서 아카이빙 자료가 있는 날짜 밑에 작은 점을 표시한다 — 확정된
    날짜는 진한 점, 아직 확정 전(오늘 등)인 날짜는 테두리만 있는 점으로 구분한다."""
    css = (
        _calendar_marker_rule(confirmed, "background:var(--hana) !important; border:none !important;")
        + _calendar_marker_rule(
            pending, "background:transparent !important; border:1px solid var(--hana) !important;"
        )
    )
    return f"<style>{css}</style>" if css.strip() else ""


def _render_sections(date_str: str, content: dict) -> None:
    _render_channel_counts(date_str, content["total_count"], content["channel_counts"])
    _render_news_list("🏠 프롭티어 관련 뉴스 TOP3", "자사 관련 소식 상위 3건입니다.", content["own_brand_news"][:3])
    _render_news_list("⚔️ 경쟁사 동향 TOP3", "경쟁사 관련 소식 상위 3건입니다.", content["competitor_news"][:3])
    _render_news_list("🌐 시장 동향 TOP3", "AI·프롭테크 등 시장 전반 소식 상위 3건입니다.", content["market_news"][:3])


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
        f"확정된 브리핑 {len(archived_dates):,}건 · 달력에서 날짜를 고르세요",
    )

    date_objs = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
    min_d, max_d = min(date_objs), max(date_objs)
    dates_with_data = set(dates)

    if "briefing_selected_date" not in st.session_state:
        st.session_state.briefing_selected_date = date_objs[0]

    confirmed_objs = {datetime.strptime(d, "%Y-%m-%d").date() for d in archived_dates}
    pending_objs = {d for d in date_objs if d not in confirmed_objs}
    marker_css = _calendar_marker_css(confirmed_objs, pending_objs)
    if marker_css:
        st.markdown(marker_css, unsafe_allow_html=True)

    picked = st.date_input(
        "\U0001F4C5 날짜 선택 (● 확정된 아카이브 · ○ 집계 중)",
        min_value=min_d, max_value=max_d, format="YYYY-MM-DD",
        key="briefing_selected_date",
    )
    picked_date = picked.strftime("%Y-%m-%d")

    if picked_date == today_str and has_today:
        st.info("\U0001F504 오늘은 아직 진행 중입니다 — 자정이 지나면 자동으로 확정됩니다.")
        content = news_feed.build_briefing_archive_content(
            today_mentions, news_feed.own_brand_names(),
            news_feed.competitor_brand_names(), news_feed.market_brand_names(),
        )
        _render_sections(today_str, content)
    elif picked_date not in dates_with_data:
        st.warning(f"{picked_date}에는 수집된 데이터가 없습니다. 데이터 보유 기간: {min_d} ~ {max_d}")
    else:
        archive = db.get_briefing_archive(picked_date)
        if archive is None:
            st.info("⏳ 아직 확정 전입니다 — 스케줄러가 곧 처리합니다.")
        else:
            _render_sections(archive["date"], archive)

    theme.footer("확정된 날짜는 고정 기록 · 오늘은 실시간 집계")
