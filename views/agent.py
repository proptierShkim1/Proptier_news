from datetime import datetime

import streamlit as st

import agent_chat
import theme
import utils

_CURRENT_LABEL = "\U0001F7E2 현재 대화"


def _session_label(session: dict, idx: int, total: int) -> str:
    started = session.get("started_at") or ""
    preview = next((t["content"][:20] for t in session.get("messages", []) if t["role"] == "user"), "")
    if idx == total - 1:
        return f"{_CURRENT_LABEL} · {started}" if started else _CURRENT_LABEL
    label = started or "이전 대화(날짜 미기록)"
    return f"{label} · {preview}" if preview else label


def render():
    theme.hero(
        "\U0001F916 AI AGENT",
        "부동산 AI 관련해서 자유롭게 대화해보세요 · 지금은 일반 대화 전용이고, "
        "수집 데이터(뉴스·정책) 기반 벡터 검색 연동은 준비 중입니다",
    )

    if not agent_chat.has_api_keys():
        st.error("GEMINI_API_KEYS가 설정되지 않아 에이전트를 사용할 수 없습니다 · .env를 확인해주세요.")
        theme.footer("AI AGENT · Gemini 연동 대기 중")
        return

    client_ip = st.session_state.get("_client_ip", "")

    if "agent_chat_sessions" not in st.session_state:
        sessions = utils.load_agent_chat_sessions(client_ip)
        if not sessions:
            sessions = [{"started_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "messages": []}]
        st.session_state["agent_chat_sessions"] = sessions

    sessions = st.session_state["agent_chat_sessions"]

    picked_idx = len(sessions) - 1
    if len(sessions) > 1:
        labels = [_session_label(s, i, len(sessions)) for i, s in enumerate(sessions)]
        picked_label = st.selectbox("\U0001F5C2️ 지난 대화", labels, index=len(labels) - 1)
        picked_idx = labels.index(picked_label)

    is_current = picked_idx == len(sessions) - 1

    if is_current and st.button("\U0001F504 새 대화 시작"):
        if sessions[-1]["messages"]:
            sessions.append({"started_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "messages": []})
            utils.save_agent_chat_sessions(client_ip, sessions)
        st.rerun()

    viewed = sessions[picked_idx]
    if not is_current and viewed.get("started_at"):
        st.caption(f"\U0001F5D3️ 대화 시작: {viewed['started_at']}")
    for turn in viewed["messages"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    if is_current:
        user_input = st.chat_input("예: 직방의 최근 1달간 동향 알려줘")
        if user_input:
            history = viewed["messages"]
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("생각 중..."):
                    reply = agent_chat.ask(history, user_input)
                st.markdown(reply)

            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})
            utils.save_agent_chat_sessions(client_ip, sessions)
    else:
        st.info("지난 대화를 보고 있어요 · 이어서 얘기하려면 위에서 '현재 대화'를 선택하세요.")

    theme.footer("AI AGENT · Gemini 연동 · 수집 데이터 기반 벡터 검색은 추후 추가")
