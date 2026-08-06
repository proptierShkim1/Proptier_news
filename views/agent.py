import streamlit as st

import agent_chat
import theme


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

    if "agent_chat_history" not in st.session_state:
        st.session_state["agent_chat_history"] = []

    if st.button("\U0001F504 대화 초기화"):
        st.session_state["agent_chat_history"] = []
        st.rerun()

    for turn in st.session_state["agent_chat_history"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    user_input = st.chat_input("예: 직방의 최근 1달간 동향 알려줘")
    if user_input:
        history = st.session_state["agent_chat_history"]
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("생각 중..."):
                reply = agent_chat.ask(history, user_input)
            st.markdown(reply)

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})

    theme.footer("AI AGENT · Gemini 연동 · 수집 데이터 기반 벡터 검색은 추후 추가")
