"""
hana_p — PDF 보고서 카드덱 템플릿. 화면 미리보기(views/report.py)와 실제 PDF 내보내기가
이 모듈이 만드는 동일한 HTML/CSS 조각을 공유한다 (레이아웃 이중 관리 방지).
"""

import math
from datetime import datetime

PAGE_PX = 1080
RANK_COLORS = ["#d4a447", "#9aa7ad", "#c9824c", "#FF8900", "#e67600"]

DECK_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
.repdeck { font-family:'Noto Sans KR','Pretendard','Malgun Gothic','Apple SD Gothic Neo',sans-serif; }
.repdeck .page { width:1080px; height:1080px; box-sizing:border-box; position:relative;
  overflow:hidden; page-break-after:always; margin:0 auto 18px; border-radius:28px; }
.repdeck .page:last-child { page-break-after:avoid; margin-bottom:0; }

.repcover { background:linear-gradient(160deg,#1c1c1e 0%,#4a2a00 55%,#ff8900 100%);
  color:#fff; padding:70px 66px 56px; display:flex; flex-direction:column; }
.repcover .brandline { display:flex; align-items:center; gap:10px; font-weight:800; font-size:22px; margin-bottom:36px; }
.repcover .brandline::before { content:""; width:34px; height:34px; border-radius:9px; background:rgba(255,255,255,.14);
  display:inline-block; }
.repcover h1 { font-size:60px; line-height:1.18; font-weight:900; margin:0 0 20px; letter-spacing:-1px; }
.repcover .date { font-size:23px; font-weight:700; margin-bottom:6px; }
.repcover .sub { font-size:19px; color:rgba(255,255,255,.75); margin-bottom:40px; }
.repcover .stats { display:flex; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18);
  border-radius:26px; padding:32px 10px; margin-bottom:38px; }
.repcover .stat { flex:1; text-align:center; }
.repcover .stat b { display:block; font-size:38px; font-weight:900; }
.repcover .stat span { font-size:17px; color:rgba(255,255,255,.7); }
.repcover .chips { display:flex; flex-wrap:wrap; gap:12px; margin-top:auto; }
.repcover .chip { background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.22);
  border-radius:999px; padding:10px 20px; font-size:18px; font-weight:700; }
.repcover .chip b { color:#ffd27a; margin-left:6px; }
.repcover .swipe { margin-top:26px; font-size:16px; color:rgba(255,255,255,.6);
  display:flex; justify-content:space-between; align-items:center; }
.repcover .dots { display:flex; gap:8px; }
.repcover .dots span { width:10px; height:10px; border-radius:50%; background:rgba(255,255,255,.3); }
.repcover .dots span.on { background:#ffd27a; width:26px; border-radius:6px; }

.repcard { background:#fff; padding:48px 56px 32px; display:flex; flex-direction:column; height:100%;
  box-sizing:border-box; }
.repcard .top { display:flex; justify-content:space-between; align-items:flex-start; flex:0 0 auto; }
.repcard .badgewrap { display:flex; align-items:center; }
.repcard .badge { width:76px; height:76px; border-radius:20px; display:flex; align-items:center;
  justify-content:center; color:#fff; font-size:36px; font-weight:900; flex:0 0 auto; }
.repcard .badge-label { margin-left:18px; }
.repcard .badge-label b { display:block; font-size:21px; font-weight:900; color:#202224; }
.repcard .badge-label span { font-size:16px; color:#7a8089; }
.repcard .datepill { background:#f3f0eb; border-radius:999px; padding:9px 20px; font-size:17px;
  color:#555; font-weight:700; height:fit-content; flex:0 0 auto; }
.repcard h2 { font-size:38px; line-height:1.32; font-weight:900; color:#202224; margin:24px 0 0;
  letter-spacing:-1px; flex:0 0 auto; max-height:160px; overflow:hidden; }
.repcard .rule { width:70px; height:5px; background:#FF8900; border-radius:3px; margin:18px 0 24px; flex:0 0 auto; }
.repcard .gist { display:flex; gap:14px; font-size:22px; line-height:1.5; color:#3a3a3d; flex:0 1 auto; min-height:0; }
.repcard .gist .ck { width:30px; height:30px; border-radius:50%; background:#FF8900; color:#fff;
  display:flex; align-items:center; justify-content:center; font-size:17px; flex:0 0 auto; margin-top:4px; }
.repcard .spacer { flex:1 1 auto; min-height:12px; }
.repcard .why { background:#fff8f0; border:1px solid #f5ddb8; border-radius:18px; padding:20px 24px;
  display:flex; gap:14px; flex:0 0 auto; }
.repcard .why .bulb { font-size:22px; }
.repcard .why p { font-size:19px; line-height:1.5; color:#5c4a2e; margin:0; }
.repcard .foot { display:flex; justify-content:space-between; align-items:center; margin-top:18px;
  padding-top:16px; border-top:1px solid #eee; font-size:16px; color:#98a3a8; flex:0 0 auto; }
.repcard .dots { display:flex; gap:8px; }
.repcard .dots span { width:9px; height:9px; border-radius:50%; background:#e2e2e2; }
.repcard .dots span.on { background:#FF8900; width:24px; border-radius:5px; }

.repsummary { background:#fff; padding:56px 60px 40px; display:flex; flex-direction:column;
  height:100%; box-sizing:border-box; }
.repsummary .shead { display:flex; justify-content:space-between; align-items:baseline;
  margin-bottom:18px; flex:0 0 auto; }
.repsummary .shead h2 { font-size:34px; font-weight:900; color:#202224; margin:0; letter-spacing:-1px; }
.repsummary .shead span { font-size:18px; color:#98a3a8; font-weight:700; }
.repsummary .srows { flex:1 1 auto; min-height:0; overflow:hidden; }
.repsummary .srow { display:flex; align-items:center; gap:16px; padding:15px 0; border-top:1px solid #eee; }
.repsummary .srow:first-child { border-top:none; }
.repsummary .srank { width:38px; height:38px; border-radius:11px; background:#f3f0eb; color:#7a8089;
  font-weight:900; font-size:17px; display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
.repsummary .ssignal { flex:0 0 auto; background:#fff1e0; color:#c2660c; border-radius:8px; padding:5px 12px;
  font-size:15px; font-weight:800; white-space:nowrap; }
.repsummary .stitle { flex:1 1 auto; font-size:20px; font-weight:700; color:#202224; line-height:1.4;
  min-width:0; }
.repsummary .smeta { flex:0 0 auto; font-size:15px; color:#98a3a8; white-space:nowrap; }
.repsummary .foot { display:flex; justify-content:space-between; align-items:center; margin-top:18px;
  padding-top:16px; border-top:1px solid #eee; font-size:16px; color:#98a3a8; flex:0 0 auto; }
.repsummary .dots { display:flex; gap:8px; }
.repsummary .dots span { width:9px; height:9px; border-radius:50%; background:#e2e2e2; }
.repsummary .dots span.on { background:#FF8900; width:24px; border-radius:5px; }
"""

SUMMARY_PAGE_SIZE = 8


def _dots_html(total, current, on_color_class="on"):
    return "".join(
        f'<span class="{on_color_class if i == current else ""}"></span>' for i in range(total)
    )


def _cover_html(items, total_pages, total_count, ai_count, summary_count=0):
    # 카테고리 칩은 선정된 상위 뉴스(items) 자체의 categories 필드를 기준으로 계산한다
    # (items가 어느 데이터 소스에서 왔는지와 무관하게 항상 실제 표시 내용과 일치함).
    category_names = []
    seen = set()
    for it in items:
        for c in it.get("categories", []):
            if c not in seen:
                seen.add(c)
                category_names.append(c)
    counts = sorted(
        ((name, sum(1 for it in items if name in it.get("categories", []))) for name in category_names),
        key=lambda x: -x[1],
    )
    chips = "".join(
        f'<span class="chip">{name}<b>{cnt}</b></span>' for name, cnt in counts[:6] if cnt
    )
    summary_note = f" · 이어서 {summary_count}건을 요약 정리했습니다" if summary_count else ""
    return f"""
    <div class="page repcover">
      <div class="brandline">부동산AI뉴스봇</div>
      <h1>부동산 AI 뉴스<br>TOP {len(items)}</h1>
      <div class="date">{datetime.now().strftime('%Y년 %m월 %d일')} 기준</div>
      <div class="sub">오늘 꼭 봐야 할 부동산 AI 소식 {len(items)}가지를 골랐습니다{summary_note}</div>
      <div class="stats">
        <div class="stat"><b>{total_count:,}</b><span>수집 기사</span></div>
        <div class="stat"><b>{ai_count:,}</b><span>관련 기사</span></div>
        <div class="stat"><b>{len(items):,}</b><span>주요 뉴스</span></div>
      </div>
      <div class="chips">{chips}</div>
      <div class="swipe"><span>옆으로 넘기며 확인하세요 →</span><div class="dots">{_dots_html(total_pages, 0)}</div></div>
    </div>
    """


def _card_html(rank, item, total_pages, top_n):
    color = RANK_COLORS[(rank - 1) % len(RANK_COLORS)]
    return f"""
    <div class="page">
      <div class="repcard">
        <div class="top">
          <div class="badgewrap">
            <div class="badge" style="background:{color}">{rank}</div>
            <div class="badge-label"><b>오늘의 주요 뉴스</b><span>부동산 AI 뉴스 TOP {top_n}</span></div>
          </div>
          <div class="datepill">{item['meta'].split('·')[0].replace(chr(0x1F552), '').strip()}</div>
        </div>
        <h2>{item['title']}</h2>
        <div class="rule"></div>
        <div class="gist"><span class="ck">✓</span><span>{item['desc'][0]}</span></div>
        <div class="spacer"></div>
        <div class="why"><span class="bulb">\U0001F4A1</span><p>{item['decision'][0]}</p></div>
        <div class="foot"><span>부동산AI뉴스봇</span><div class="dots">{_dots_html(total_pages, rank)}</div></div>
      </div>
    </div>
    """


def _summary_page_html(items, rank_offset, total_pages, current_page):
    rows = "".join(
        f"""
        <div class="srow">
          <div class="srank">{rank_offset + i}</div>
          <div class="ssignal">{item['signal']}</div>
          <div class="stitle">{item['title']}</div>
          <div class="smeta">{item.get('firm', '')} · {item.get('date', '')}</div>
        </div>
        """
        for i, item in enumerate(items)
    )
    return f"""
    <div class="page">
      <div class="repsummary">
        <div class="shead"><h2>오늘의 뉴스 요약</h2>
          <span>{rank_offset}~{rank_offset + len(items) - 1}위</span></div>
        <div class="srows">{rows}</div>
        <div class="foot"><span>부동산AI뉴스봇</span><div class="dots">{_dots_html(total_pages, current_page)}</div></div>
      </div>
    </div>
    """


def _chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def summary_page_count(n: int) -> int:
    """summary_items가 n건일 때 요약 목록 페이지가 몇 장 생기는지 (SUMMARY_PAGE_SIZE건씩 묶음)."""
    return math.ceil(n / SUMMARY_PAGE_SIZE) if n else 0


def build_deck_html(items, total_count=0, ai_count=0, summary_items=None):
    """미리보기(st.markdown)와 PDF 내보내기(Playwright)가 공유하는 콘텐츠 HTML을 만든다.
    <style> 태그는 포함하지 않는다 — Streamlit 쪽은 theme.inject()가 한 번만 주입하는
    전역 스타일(DECK_CSS 포함)에 얹혀 렌더링되고, PDF 내보내기 쪽은 generate_pdf_bytes()가
    별도로 <style>을 붙여 완성한다. st.markdown 안에 <style>을 직접 넣으면 태그 자체가
    본문에 텍스트로 노출되는 문제가 있어 이렇게 분리했다.
    각 줄 앞의 들여쓰기는 제거해서 반환한다.
    total_count/ai_count는 표지 통계 칩("수집 기사"/"관련 기사")에 쓰이며, 호출부(뉴스
    데이터를 실제로 조회한 쪽)가 계산해서 넘겨준다 — 이 모듈은 데이터 소스를 모른다.
    summary_items는 items(상세 카드) 뒤에 이어붙일 간략 요약 목록이다 — 상세 카드 몇
    건만으로는 그날 수집된 전체 내용을 대표하지 못한다는 피드백에 따라, 상세 카드 뒤에
    SUMMARY_PAGE_SIZE건씩 묶은 목록 페이지로 나머지를 커버한다."""
    summary_items = summary_items or []
    summary_chunks = _chunk(summary_items, SUMMARY_PAGE_SIZE)
    total_pages = 1 + len(items) + len(summary_chunks)
    pages = [_cover_html(items, total_pages, total_count, ai_count, len(summary_items))]
    pages += [_card_html(i, item, total_pages, len(items)) for i, item in enumerate(items, start=1)]
    rank_offset = len(items) + 1
    for idx, chunk in enumerate(summary_chunks):
        pages.append(_summary_page_html(chunk, rank_offset, total_pages, len(items) + 1 + idx))
        rank_offset += len(chunk)
    html = f'<div class="repdeck">{"".join(pages)}</div>'
    return "\n".join(line.strip() for line in html.split("\n"))


def generate_pdf_bytes(items, total_count=0, ai_count=0, summary_items=None) -> bytes:
    """build_deck_html()과 동일한 레이아웃을 실제 PDF 바이트로 렌더링한다 (Playwright/Chromium).
    Streamlit 전역 스타일이 없는 독립 렌더링이므로 여기서는 <style>을 직접 붙인다.

    Windows에서는 Streamlit 서버(Tornado)가 프로세스 전역 asyncio 이벤트 루프 정책을
    SelectorEventLoop로 강제해두는데, Playwright의 동기 API는 브라우저를 서브프로세스로
    띄우기 위해 ProactorEventLoop가 필요하다 (SelectorEventLoop는 Windows에서 서브프로세스
    생성을 지원하지 않아 NotImplementedError가 남). 그래서 Playwright를 호출하는 동안만
    정책을 Proactor로 바꿨다가 끝나면 원래대로 되돌린다 — 이미 떠 있는 Tornado 루프 자체는
    정책이 아니라 루프 객체 참조로 계속 동작하므로 영향받지 않는다."""
    import asyncio
    import sys

    from playwright.sync_api import sync_playwright

    html = (
        f'<meta charset="utf-8"><style>{DECK_CSS}</style>'
        f'{build_deck_html(items, total_count, ai_count, summary_items)}'
    )

    old_policy = None
    if sys.platform == "win32":
        old_policy = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            # 배포 서버에는 한글 폰트가 설치되어 있지 않을 수 있어 DECK_CSS가 구글 폰트
            # CDN에서 'Noto Sans KR'을 내려받는다 — @font-face 다운로드는 'load' 이벤트
            # 이후에도 비동기로 계속될 수 있으므로, 폰트가 실제로 적용된 뒤에 PDF를
            # 찍어야 한글이 빈 사각형(tofu)으로 렌더링되지 않는다.
            page.evaluate("document.fonts.ready")
            pdf_bytes = page.pdf(
                width=f"{PAGE_PX}px", height=f"{PAGE_PX}px", print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            browser.close()
    finally:
        if old_policy is not None:
            asyncio.set_event_loop_policy(old_policy)
    return pdf_bytes
