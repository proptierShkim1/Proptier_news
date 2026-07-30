import streamlit as st

import theme
import db
from access_control import is_allowed, is_admin
from report_pdf import DECK_CSS
from scheduler import start_scheduler_thread
from views import news_today, firms, briefings, search, report, settings

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

if not is_allowed(_client_ip):
    st.markdown("## \U0001F512 접근 제한")
    st.error(f"허용된 IP에서만 접근할 수 있습니다.\n\n현재 접속 IP: `{_client_ip}`")
    st.stop()

_is_admin = is_admin(_client_ip)
st.session_state["_is_admin"] = _is_admin

pages = [
    st.Page(news_today.render, title="오늘의 뉴스", icon="\U0001F4F0", url_path="news", default=True),
    st.Page(firms.render, title="부동산사 동향", icon="\U0001F3E2", url_path="firms"),
    st.Page(briefings.render, title="브리핑", icon="\U0001F4DD", url_path="briefings"),
    st.Page(search.render, title="뉴스 검색", icon="\U0001F50D", url_path="search"),
    st.Page(report.render, title="PDF 보고서", icon="\U0001F4C4", url_path="report"),
]
if _is_admin:
    pages.append(st.Page(settings.render, title="설정", icon="\U00002699", url_path="settings"))

nav = st.navigation(pages, position="top")
nav.run()
