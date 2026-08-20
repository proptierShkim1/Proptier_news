import uuid

import streamlit as st
import streamlit.components.v1 as components

import theme
import db
from access_control import is_admin
from report_pdf import DECK_CSS
from scheduler import start_scheduler_thread
from views import agent, news_today, firms, briefings, search, report, policy_news, settings

st.set_page_config(page_title="부동산 AI 주요뉴스", page_icon="\U0001F3E0", layout="wide")
theme.inject()
st.markdown(f"<style>{DECK_CSS}</style>", unsafe_allow_html=True)

db.init_db()
start_scheduler_thread()


def _get_client_ip() -> str:
    try:
        from streamlit.runtime.context import _get_client_context
        ctx = _get_client_context()
        return (ctx.remote_ip or "") if ctx else ""
    except Exception:
        pass
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        from streamlit.runtime import get_instance
        ctx = get_script_run_ctx()
        session = get_instance().get_session_info(ctx.session_id)
        return session.client.request.remote_ip or ""
    except Exception:
        return ""


def _get_or_create_client_uid() -> str:
    """브라우저별 영구 식별자를 얻는다. AI AGENT 채팅 이력을 접속 IP 대신 이 값으로
    구분해, 같은 사람이 IP가 바뀌어도(DHCP 재할당, 유/무선 전환 등) 이전 대화를 이어가고,
    사내망 특성상 여러 사람이 같은 IP를 공유하더라도(공유기/게이트웨이) 대화가 섞이지
    않게 한다. 이 앱은 로그인이 없는 내부망 도구라 이 정도가 현실적인 절충.

    st.context.cookies(읽기 전용, 요청 시점 쿠키)에 hana_p_uid가 있으면 그대로 쓴다.
    없으면(최초 방문) 새로 하나 만들어 이번 실행에 즉시 쓰고, JS로 쿠키를 심어 다음
    방문부터는 st.context.cookies에서 바로 읽히게 한다.

    처음엔 components.html 안에서 JS로 window.parent.location을 바꿔 같은 URL에
    ?uid=...를 붙이는 방식을 시도했는데, Streamlit이 컴포넌트 iframe에 심는 sandbox
    속성에 allow-top-navigation이 없어 최상위 프레임 이동이 브라우저에서 조용히
    막혔다(Playwright로 콘솔 에러를 직접 확인). document.cookie 쓰기는
    allow-same-origin만으로 충분해 막히지 않으므로, 리다이렉트 없이 쿠키만 심는 이
    방식으로 바꿨다."""
    uid = st.context.cookies.get("hana_p_uid", "")
    if uid:
        return uid
    uid = str(uuid.uuid4())
    components.html(
        f"""
        <script>
        document.cookie = 'hana_p_uid={uid};path=/;max-age=31536000;samesite=lax';
        </script>
        """,
        height=0,
    )
    return uid


_client_ip = _get_client_ip()
st.session_state["_client_ip"] = _client_ip

_client_uid = _get_or_create_client_uid()
st.session_state["_client_uid"] = _client_uid

_is_admin = is_admin(_client_ip)
st.session_state["_is_admin"] = _is_admin

agent_page = st.Page(agent.render, title="AI AGENT", icon="\U0001F916", url_path="agent")

pages = [
    st.Page(news_today.render, title="오늘의 뉴스", icon="\U0001F4F0", url_path="news", default=True),
    st.Page(firms.render, title="부동산사 동향", icon="\U0001F3E2", url_path="firms"),
    st.Page(briefings.render, title="브리핑", icon="\U0001F4DD", url_path="briefings"),
    st.Page(policy_news.render, title="정책 뉴스", icon="\U0001F3DB", url_path="policy"),
    st.Page(search.render, title="뉴스 검색", icon="\U0001F50D", url_path="search"),
    st.Page(report.render, title="PDF 보고서", icon="\U0001F4C4", url_path="report"),
    agent_page,
]
if _is_admin:
    pages.append(st.Page(settings.render, title="설정", icon="\U00002699", url_path="settings"))

nav = st.navigation(pages, position="top")
if st.session_state.get("_last_logged_page") != nav.title:
    db.log_activity(_client_ip, nav.title, "페이지 방문")
    st.session_state["_last_logged_page"] = nav.title
# st.navigation(...).run() 뒤에 오는 코드는 실제로 렌더링되지 않는다(실측 확인) —
# 모든 화면 공통 UI(플로팅 버튼)는 반드시 run() 이전에 호출해야 한다. position:fixed라
# 화면상 위치는 호출 순서와 무관하다.
theme.floating_actions(agent_page)
nav.run()
