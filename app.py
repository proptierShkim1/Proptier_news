import streamlit as st

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


_client_ip = _get_client_ip()
st.session_state["_client_ip"] = _client_ip

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
