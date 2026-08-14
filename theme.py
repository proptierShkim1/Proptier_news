import altair as alt
import pandas as pd
import streamlit as st

from utils import escape_html

CSS = """
<style>
:root{
  --hana:#FF8900; --hana-deep:#e67600; --hana-dark:#202224;
  --hana-bright:#ffab33; --hana-mint:#fff1e0; --gold:#d4a447;
  --ink:#202224; --ink-soft:#4b4f58; --muted:#7a8089;
  --line:#e7e2dc; --bg:#faf7f4;
  --shadow-sm:0 3px 12px rgba(32,34,36,.05);
  --shadow-md:0 14px 38px rgba(32,34,36,.09);
}
.stApp {
  background: radial-gradient(circle at 8% 3%, rgba(255,137,0,.09), transparent 24rem),
              radial-gradient(circle at 94% 18%, rgba(230,118,0,.07), transparent 28rem), var(--bg);
}
.block-container {max-width:1120px; padding-top:1.5rem; padding-bottom:3rem;}
#MainMenu, footer {visibility:hidden;}

/* ----- 채팅 입력창(st.chat_input)이 본문과 같은 폭으로 보이도록 ----- */
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {
  max-width:1120px!important; margin-left:auto!important; margin-right:auto!important;
}

.hero {position:relative; overflow:hidden; border-radius:24px; padding:36px 38px 34px;
       margin-bottom:16px; color:#fff;
       background:linear-gradient(125deg,#1c1c1e 0%,#4a2a00 48%,#ff8900 100%);
       box-shadow:0 20px 50px rgba(74,42,0,.25);}
.hero .brand {display:inline-flex; align-items:center; gap:7px; font-size:.68rem; font-weight:800;
       letter-spacing:1px; margin-bottom:14px; padding:5px 11px;
       background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.24); border-radius:999px;}
.hero .brand::before {content:""; width:6px; height:6px; border-radius:50%; background:#ffb84d;}
.hero h1 {font-size:2.1rem; font-weight:850; margin:0; letter-spacing:-1.3px; color:#fff;}
.hero p {margin:12px 0 0; color:rgba(255,255,255,.79); font-size:.87rem; max-width:700px;}
.hero-side {border:1px solid rgba(255,255,255,.18); background:rgba(30,20,10,.35);
       border-radius:18px; padding:16px 18px; margin-top:16px; display:inline-block;}
.hero-side .hs-label {font-size:.65rem; font-weight:800; letter-spacing:1.2px; color:#ffd9a3; text-transform:uppercase;}
.hero-side .hs-value {font-size:1.4rem; font-weight:850; margin-top:4px; color:#fff;}
.hero-side .hs-note {font-size:.72rem; color:rgba(255,255,255,.68); margin-top:4px;}

.metric-box {background:rgba(255,255,255,.92); border:1px solid var(--line); border-radius:17px;
             padding:16px 18px 15px; box-shadow:var(--shadow-sm);}
.metric-box .mi {display:inline-grid; place-items:center; width:28px; height:28px; float:right;
             background:#fff1e0; border-radius:9px; font-size:.82rem;}
.metric-box .v {font-size:1.5rem; font-weight:850; letter-spacing:-.6px; color:var(--hana-dark); line-height:1.1;}
.metric-box .l {font-size:.69rem; color:var(--muted); margin-top:6px; font-weight:750;}

.exec-eyebrow {font-size:.61rem; font-weight:850; letter-spacing:1.2px; color:var(--hana);}
h2.brief-h {font-size:1.24rem; letter-spacing:-.5px; margin:3px 0 10px;}
.brief-lead {border:1px solid var(--line); border-radius:18px; background:linear-gradient(145deg,#fff 55%,#fff6ec);
       box-shadow:var(--shadow-sm); padding:22px 24px; height:100%;}
.brief-tag {display:block; color:var(--hana); font-size:.61rem; font-weight:850; letter-spacing:1px; margin-bottom:8px;}
.brief-lead a {display:block; color:var(--ink); text-decoration:none; font-weight:850; font-size:1.2rem; line-height:1.45;}
.brief-lead p {color:var(--ink-soft); font-size:.86rem; line-height:1.72; margin:11px 0 15px;}
.brief-why {display:grid; grid-template-columns:90px 1fr; gap:10px; border-top:1px solid #f0e9e0;
       padding-top:12px; font-size:.78rem;}
.brief-why b {color:var(--hana-deep); font-size:.66rem; letter-spacing:.5px; text-transform:uppercase;}
.brief-why span {color:var(--ink-soft); line-height:1.6;}
.brief-stat {border:1px solid var(--line); border-radius:18px; background:#fff; box-shadow:var(--shadow-sm);
       padding:16px 18px; margin-bottom:10px;}
.brief-stat strong {display:inline-block; color:var(--hana-dark); font-size:1.3rem; margin-right:7px;}
.brief-stat em {font-style:normal; color:var(--hana); font-size:.68rem; font-weight:800;}
.brief-stat p {color:var(--muted); font-size:.72rem; line-height:1.55; margin:5px 0 0;}
.brief-stat.action {background:#2a1c10; border-color:#2a1c10;}
.brief-stat.action .brief-tag {color:#ffb84d;}
.brief-stat.action strong {color:#fff;}
.brief-stat.action em {color:#ffb84d;}
.brief-stat.action p {color:rgba(255,255,255,.68);}

.range-note {background:rgba(255,241,224,.7); border:1px solid #f0d9b8; border-radius:13px;
             padding:10px 14px; font-size:.77rem; color:#4a3b2e; margin:6px 0 10px; line-height:1.55;}

h2.sec {display:flex; align-items:center; gap:10px; font-size:1.12rem; font-weight:850;
        letter-spacing:-.35px; color:var(--ink); margin:25px 0 4px;}
h2.sec::before {content:"INTELLIGENCE RANKING"; font-size:.61rem; letter-spacing:1px;
        color:var(--hana); background:var(--hana-mint); padding:4px 8px; border-radius:6px;}
.sec-note {color:var(--muted); font-size:.79rem; margin:0 0 12px;}

.sl-item {position:relative; padding:18px 20px 16px; background:rgba(255,255,255,.97);
     border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow-sm); margin-bottom:10px;}
.sl-item.top1 {border-left:5px solid var(--gold);}
.sl-item.top2 {border-left:5px solid #9aa7ad;}
.sl-item.top3 {border-left:5px solid #c9824c;}
.sl-signal {display:inline-flex; color:var(--hana-deep); background:#fff1e0; border-radius:7px;
     padding:2px 8px; margin:0 0 8px 0; font-size:.65rem; font-weight:800;}
.sl-head {display:flex; align-items:baseline; gap:11px; flex-wrap:wrap;}
.sl-rank {min-width:26px; text-align:center; font-weight:800; color:var(--hana); font-size:0.92rem;}
.sl-title {flex:1; color:var(--ink); text-decoration:none; font-weight:700; font-size:1.02rem; line-height:1.48;}
.sl-title:hover {color:var(--hana); text-decoration:underline;}
.sl-score {background:var(--hana-mint); color:var(--hana-deep); font-weight:700; border-radius:20px;
     padding:2px 11px; font-size:0.74rem; white-space:nowrap;}
.sl-desc {margin:9px 0 0 0; padding:9px 12px 9px 14px; border-radius:10px; background:#faf7f4;
     border:1px solid #f0ece6; list-style:none;}
.sl-desc li {font-size:0.88rem; line-height:1.7; color:var(--ink-soft); margin:4px 0; padding-left:15px; position:relative;}
.sl-desc li::before {content:"▪"; color:var(--hana); position:absolute; left:0;}
.insight {background:linear-gradient(180deg,#fff8f0,#fff1e0); border:1px solid #f5ddb8; border-radius:12px;
          padding:11px 15px; margin-top:12px;}
.insight-title {font-size:0.79rem; font-weight:800; color:var(--hana-deep); margin-bottom:5px;}
.insight ul {margin:0; padding:0; list-style:none;}
.insight li {font-size:0.83rem; color:#4a3b2e; line-height:1.6; margin:3px 0; padding-left:15px; position:relative;}
.insight li::before {content:"▸"; color:var(--hana); position:absolute; left:0;}
.sl-meta {color:var(--muted); font-size:0.74rem; margin:8px 0 0 0; padding-top:7px; border-top:1px solid #eef3f3;}

.footer {text-align:center; color:#93a3a7; font-size:0.76rem; margin:26px 0 8px; line-height:1.6;}

.stTabs [data-baseweb="tab-list"] {gap:6px;}
.stTabs [data-baseweb="tab"] {border:1px solid #d3dedf; background:#fff; border-radius:22px;
     padding:6px 16px; font-weight:700; color:var(--ink-soft);}
.stTabs [aria-selected="true"] {background:var(--hana-dark)!important; color:#fff!important; border-color:var(--hana-dark)!important;}

.pbtn-row button {border-radius:20px!important;}

/* ----- 상단 내비게이션 (st.navigation position=top) ----- */
[data-testid="stHeader"] {
  background:#fff!important; border-bottom:1px solid var(--line);
  box-shadow:0 2px 10px rgba(32,34,36,.05);
}
[data-testid="stTopNavLink"], [data-testid="stTopNavDropdownLink"],
[data-testid="stTopNavLink"] *, [data-testid="stTopNavDropdownLink"] * {
  color:var(--ink-soft)!important; font-weight:700!important;
  border-radius:10px!important; background:transparent!important; fill:var(--ink-soft)!important;
}
[data-testid="stTopNavLink"]:hover, [data-testid="stTopNavDropdownLink"]:hover,
[data-testid="stTopNavLink"]:hover *, [data-testid="stTopNavDropdownLink"]:hover * {
  color:var(--hana-deep)!important; background:var(--hana-mint)!important; fill:var(--hana-deep)!important;
}
[data-testid="stTopNavLink"][aria-current="page"],
[data-testid="stTopNavLink"][aria-current="page"] * {
  color:#fff!important; background:var(--hana)!important; border-radius:999px!important; fill:#fff!important;
}
[data-testid="stTopNavLinkContainer"] {background:transparent!important;}
[data-testid="stTopNavSection"], [data-testid="stTopNavSection"] * {color:var(--ink-soft)!important;}

/* ----- 이슈 아코디언 (부동산사 동향) ----- */
.iss {border:1px solid var(--line); border-radius:14px; background:#fff; box-shadow:var(--shadow-sm);
      padding:2px 16px; margin-bottom:8px;}
.iss summary {list-style:none; cursor:pointer; padding:12px 2px; display:flex; align-items:center;
      gap:10px; flex-wrap:wrap;}
.iss summary::-webkit-details-marker {display:none;}
.iss-cat {border-radius:8px; padding:3px 9px; font-size:.72rem; font-weight:700; white-space:nowrap;}
.iss-title {flex:1; font-weight:700; color:var(--ink); font-size:.94rem; min-width:200px;}
.iss-meta {color:var(--muted); font-size:.78rem; white-space:nowrap;}
.iss-live {background:var(--hana-mint); color:var(--hana-deep); border-radius:10px; padding:2px 9px;
      font-size:.7rem; font-weight:700; white-space:nowrap;}
.iss-done {background:#eef2f3; color:#6d8085; border-radius:10px; padding:2px 9px; font-size:.7rem; font-weight:700;}
.iss-arts {margin:0 0 10px; padding:0; list-style:none;}
.iss-arts li {padding:7px 2px; border-top:1px solid #f2eee9; font-size:.86rem; display:flex; gap:10px;}
.iss-arts a {color:var(--ink); text-decoration:none; font-weight:600;}
.iss-arts a:hover {color:var(--hana); text-decoration:underline;}

/* ----- 브리핑 아카이브 ----- */
.bf-item {display:block; width:100%; text-align:left; border:1px solid var(--line); background:#fff;
      border-radius:12px; padding:10px 14px; margin-bottom:6px; cursor:pointer; font-size:.86rem;
      font-weight:700; color:var(--ink-soft);}
.bf-item.on, .bf-item:hover {border-color:var(--hana); color:var(--hana-deep); background:var(--hana-mint);}

/* ----- 뉴스 검색 ----- */
.sc-box {background:#fff; border:1px solid var(--line); border-radius:16px; padding:16px 18px;
      box-shadow:var(--shadow-sm); margin-bottom:14px;}
.plabel {font-size:.78rem; font-weight:700; color:var(--muted);}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title, subtitle, brand="PROPTIER · AI INTELLIGENCE",
         side_label=None, side_value=None, side_note=None):
    side_html = ""
    if side_value:
        side_html = f"""<div class="hero-side">
    <div class="hs-label">{side_label}</div>
    <div class="hs-value">{side_value}</div>
    <div class="hs-note">{side_note}</div>
  </div>"""
    st.markdown(f"""
    <div class="hero">
      <span class="brand">{brand}</span>
      <h1>{title}</h1>
      <p>{subtitle}</p>
      {side_html}
    </div>
    """, unsafe_allow_html=True)


def metric_row(metrics):
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        col.markdown(f"""
        <div class="metric-box"><span class="mi">{m['icon']}</span>
        <div class="v">{m['value']}</div><div class="l">{m['label']}</div></div>
        """, unsafe_allow_html=True)


def bar_chart(data: dict, height: int = 160, color: str = "#FF8900"):
    """st.bar_chart는 항목이 많으면 x축 레이블을 자동으로 비스듬히/세로로 돌리는데,
    그걸 항상 가로로 고정하기 위해 Altair로 직접 그린다."""
    df = pd.DataFrame({"label": list(data.keys()), "value": list(data.values())})
    chart = (
        alt.Chart(df)
        .mark_bar(color=color)
        .encode(
            x=alt.X("label:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("value:Q", axis=alt.Axis(title=None)),
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def _news_card_html(item, rank_display, top_class=""):
    desc_html = "".join(f"<li>{escape_html(d)}</li>" for d in item["desc"])
    decision_html = "".join(f"<li>{escape_html(d)}</li>" for d in item["decision"])
    return f"""
    <div class="sl-item {top_class}">
      <div class="sl-signal">{item['signal']}</div>
      <div class="sl-head"><span class="sl-rank">{rank_display}</span>
        <a class="sl-title" href="{escape_html(item['url'])}" target="_blank">{escape_html(item['title'])}</a>
        <span class="sl-score">점수 {item['score']}</span></div>
      <ul class="sl-desc">{desc_html}</ul>
      <div class="insight"><div class="insight-title">DECISION POINT · 의사결정 포인트</div>
        <ul>{decision_html}</ul></div>
      <div class="sl-meta">{escape_html(item['meta'])}</div>
    </div>
    """


def news_card(item, rank_display, top_class=""):
    st.markdown(_news_card_html(item, rank_display, top_class), unsafe_allow_html=True)


def _policy_signal_card_html(item, rank_display, top_class=""):
    return f"""
    <div class="sl-item {top_class}">
      <div class="sl-signal">{item['signal']}</div>
      <div class="sl-head"><span class="sl-rank">{rank_display}</span>
        <a class="sl-title" href="{escape_html(item['url'])}" target="_blank">{escape_html(item['title'])}</a>
        <span class="sl-score">점수 {item['score']}</span></div>
      <div class="sl-meta">{escape_html(item['source'])} · {escape_html(item['department'])} · 조회 {item['view_count']:,} · {escape_html(item['announced_at'])}</div>
    </div>
    """


def policy_signal_card(item, rank_display, top_class=""):
    st.markdown(_policy_signal_card_html(item, rank_display, top_class), unsafe_allow_html=True)


def footer(note):
    st.markdown(f'<div class="footer">프롭티어 · 부동산 AI 주요뉴스 봇 &nbsp;|&nbsp; {note}</div>', unsafe_allow_html=True)


def floating_actions(agent_page):
    """모든 화면 공통으로 우하단에 떠 있는 "맨 위로"/"AI AGENT로 이동" 버튼. app.py가
    st.navigation(...).run() **이전에** 호출해야 한다 — run() 뒤에 오는 코드는 실제로
    렌더링되지 않는다는 걸 실측으로 확인함(position:fixed라 화면상 위치는 호출 순서와
    무관하지만, 애초에 실행조차 안 되면 소용없다).

    맨 위로 버튼은 onclick 인라인 JS가 아니라 순수 앵커(#fragment) 링크다 — Streamlit이
    unsafe_allow_html로 넣은 HTML을 React가 파싱하면서 onclick 같은 인라인 이벤트
    속성을 통째로 제거해버리는 걸 실측으로 확인함(콘솔에 "Minified React error #231
    ... args[]=onClick&args[]=string" 발생, 렌더링된 DOM에 onclick 속성 자체가 사라져
    있었음). 그래서 이 함수가 호출되는 시점(run() 이전 = 페이지 콘텐츠보다 먼저
    렌더링됨)에 스크롤 최상단 지점에 보이지 않는 마커(#hp-scroll-top)를 심어두고,
    버튼은 그 마커로 가는 순수 `<a href="#...">` 링크로만 구현한다 — 브라우저 기본
    앵커 스크롤 동작이라 JS 없이도 동작하고, 실제 스크롤 컨테이너가 document가 아니라
    [data-testid="stMain"]이어도 문제없이 그 안에서 스크롤된다.

    AI AGENT 버튼은 st.switch_page로 이동해 세션 상태를 유지한 채(대화 이력 등)
    전환된다."""
    st.markdown("""
    <style>
    [data-testid="stMain"] { scroll-behavior: smooth; }

    #hp-top-fab {
      position: fixed; right: 24px; bottom: 92px; z-index: 9999;
      width: 50px; height: 50px; border-radius: 50%;
      background: #fff; color: var(--hana-deep); text-decoration: none;
      border: 2px solid var(--hana);
      display: flex; align-items: center; justify-content: center;
      font-size: 1.2rem; box-shadow: var(--shadow-md);
      transition: transform .15s ease, background .15s ease;
    }
    #hp-top-fab:hover { transform: translateY(-2px); color: #fff; background: var(--hana); }

    div[class*="st-key-hp_agent_fab"] {
      position: fixed; right: 24px; bottom: 24px; z-index: 9999;
      width: 50px; height: 50px;
    }
    div[class*="st-key-hp_agent_fab"] button {
      width: 50px; height: 50px; border-radius: 50%; padding: 0;
      background: var(--hana); color: #fff; border: none;
      font-size: 1.2rem; box-shadow: var(--shadow-md);
      transition: transform .15s ease;
    }
    div[class*="st-key-hp_agent_fab"] button:hover {
      background: var(--hana-deep); color: #fff; transform: translateY(-2px);
    }
    </style>
    <span id="hp-scroll-top"></span>
    <a id="hp-top-fab" href="#hp-scroll-top" title="맨 위로">\U00002B06\U0000FE0F</a>
    """, unsafe_allow_html=True)

    if st.button("\U0001F916", key="hp_agent_fab", help="AI AGENT로 이동"):
        st.switch_page(agent_page)
