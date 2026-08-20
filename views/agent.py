from datetime import datetime

import streamlit as st

import agent_chat
import db
import theme
import utils
import vectorizer

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
        "부동산 AI 관련해서 자유롭게 대화해보세요 · 수집된 뉴스·정책 데이터를 벡터 검색으로 "
        "찾아 답변에 참고합니다",
    )

    if not agent_chat.has_api_keys():
        st.error("GEMINI_API_KEYS가 설정되지 않아 에이전트를 사용할 수 없습니다 · .env를 확인해주세요.")
        theme.footer("AI AGENT · Gemini 연동 대기 중")
        return

    client_ip = st.session_state.get("_client_ip", "")
    # 채팅 이력은 접속 IP가 아니라 브라우저별 영구 식별자(_client_uid, app.py에서 쿠키로
    # 발급)로 구분한다 — 사내망 특성상 여러 사람이 같은 IP를 공유하거나 한 사람의 IP가
    # DHCP로 바뀌는 상황에서도 대화가 섞이거나 끊기지 않게 하기 위함. 활동 로그(누가/언제
    # 접속했는지)는 여전히 IP 기준이라 client_ip를 그대로 쓴다.
    client_uid = st.session_state.get("_client_uid", "")

    if "agent_chat_sessions" not in st.session_state:
        sessions = db.get_agent_chat_sessions(client_uid)
        if not sessions:
            sessions = [{"started_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "messages": []}]
        st.session_state["agent_chat_sessions"] = sessions

    sessions = st.session_state["agent_chat_sessions"]
    always_show_hybrid_search = utils.load_agent_settings()["always_show_hybrid_search"]

    picked_idx = len(sessions) - 1
    if len(sessions) > 1:
        labels = [_session_label(s, i, len(sessions)) for i, s in enumerate(sessions)]
        picked_label = st.selectbox("\U0001F5C2️ 지난 대화", labels, index=len(labels) - 1)
        picked_idx = labels.index(picked_label)

    is_current = picked_idx == len(sessions) - 1

    if is_current and st.button("\U0001F504 새 대화 시작"):
        if sessions[-1]["messages"]:
            # 새 세션은 메시지가 생기기 전까지 DB에 쓸 게 없다 — 첫 메시지가
            # append_agent_chat_message()로 저장될 때 이 started_at으로 자연스럽게
            # 새 세션이 생긴다.
            sessions.append({"started_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "messages": []})
        st.rerun()

    viewed = sessions[picked_idx]
    if not is_current and viewed.get("started_at"):
        st.caption(f"\U0001F5D3️ 대화 시작: {viewed['started_at']}")
    for idx, turn in enumerate(viewed["messages"]):
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if (
                is_current and turn["role"] == "assistant"
                and (turn.get("insufficient") or always_show_hybrid_search)
                and not turn.get("web_search_done")
            ):
                if st.button("\U0001F310 Hybrid Search 실행", key=f"web_search_btn_{idx}"):
                    question = viewed["messages"][idx - 1]["content"]
                    with st.spinner("웹 검색 중..."):
                        web_reply = agent_chat.ask_with_web_search(viewed["messages"][:idx - 1], question)
                    turn["web_search_done"] = True
                    if turn.get("id") is not None:
                        db.mark_agent_chat_message_web_search_done(turn["id"])
                    web_content = f"\U0001F310 **웹 검색 기반 답변**\n\n{web_reply}"
                    new_id = db.append_agent_chat_message(
                        client_uid, viewed["started_at"], "assistant", web_content,
                    )
                    viewed["messages"].append({"id": new_id, "role": "assistant", "content": web_content})
                    st.rerun()

    if is_current:
        user_input = st.chat_input("예: 직방의 최근 1달간 동향 알려줘")
        if user_input:
            db.log_activity(client_ip, "AI AGENT", "채팅 전송", user_input[:200])
            history = viewed["messages"]
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("생각 중..."):
                    is_stats_question = agent_chat.looks_like_stats_only_question(user_input)
                    if is_stats_question:
                        # 지표 도구만으로 답할 수 있는 게 명백한 질문은 벡터 검색(임베딩 API
                        # 호출 2회)을 건너뛴다 — 동시 사용자가 늘어날수록 이 절감이 커진다.
                        context = ""
                        sufficient = True
                    else:
                        mention_hits = vectorizer.search_similar_mentions(user_input, top_k=5)
                        policy_hits = vectorizer.search_similar_policy_events(user_input, top_k=3)
                        context = agent_chat.build_grounding_context(mention_hits, policy_hits)
                        sufficient = agent_chat.is_grounding_sufficient(mention_hits, policy_hits)
                    reply = agent_chat.ask(history, user_input, context=context)
                st.markdown(reply)

            user_id = db.append_agent_chat_message(client_uid, viewed["started_at"], "user", user_input)
            assistant_id = db.append_agent_chat_message(
                client_uid, viewed["started_at"], "assistant", reply, insufficient=not sufficient,
            )
            assistant_turn = {"id": assistant_id, "role": "assistant", "content": reply}
            if not sufficient:
                assistant_turn["insufficient"] = True
            history.append({"id": user_id, "role": "user", "content": user_input})
            history.append(assistant_turn)
            st.rerun()
    else:
        st.info("지난 대화를 보고 있어요 · 이어서 얘기하려면 위에서 '현재 대화'를 선택하세요.")

    theme.footer("AI AGENT · Gemini 연동 · 수집 데이터 기반 벡터 검색")
