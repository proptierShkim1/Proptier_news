"""
hana_p — "AI AGENT" 페이지용 범용 Gemini 대화. summarizer.py와 같은 자격증명(GEMINI_API_KEYS/
GEMINI_MODEL)을 재사용한다.

매 메시지마다 새 genai.Client()로 대화를 재구성한다(이전 히스토리를 seed로 주입) — Streamlit
재실행이 다른 스레드에서 스크립트를 돌릴 수 있어, SDK의 chat 세션 객체를 session_state에
그대로 들고 있다가 재사용하면 내부 HTTP 클라이언트가 닫힌 상태로 남아 "client has been closed"
오류가 나는 걸 실제로 확인했다. 그래서 히스토리는 순수 텍스트로만 들고 있다가, 메시지를 보낼
때마다 새 세션에 주입하는 방식으로 바꿨다 — 여러 키로 failover하기도 이 방식이 더 쉽다.

벡터 검색/수집 데이터(mentions·policy_events) 연동은 아직 없다 — 일단 순수 LLM 대화만
지원하고, 데이터 그라운딩은 벡터 데이터 준비된 뒤 추가할 예정이다.
"""

from google import genai
from google.genai import types

import summarizer

_SYSTEM_INSTRUCTION = (
    "너는 프롭티어(부동산 AI 프롭테크 기업) 사내에서 쓰는 어시스턴트야. 한국어로 "
    "친근하고 간결하게 답변해. 아직 사내에서 수집한 뉴스·정책 데이터에는 연결되어 있지 않으니, "
    "관련 질문을 받으면 일반적인 지식으로 답하되 사내 데이터 기반 답변은 아니라는 점을 밝혀줘."
)


def has_api_keys() -> bool:
    return bool(summarizer._load_api_keys())


def ask(history: list[dict], message: str) -> str:
    """history는 이번 메시지를 제외한 이전 턴들 [{"role": "user"|"assistant", "content": str}, ...].
    매번 새 Client/chat 세션을 만들어 history를 주입한 뒤 message를 보내고 응답 텍스트를 반환한다.
    키가 없거나 모든 키 호출이 실패해도 예외를 던지지 않고 에러 메시지 문자열을 반환한다."""
    keys = summarizer._load_api_keys()
    if not keys:
        return "GEMINI_API_KEYS가 설정되지 않아 에이전트를 사용할 수 없습니다."

    seeded_history = [
        types.Content(
            role="user" if turn["role"] == "user" else "model",
            parts=[types.Part(text=turn["content"])],
        )
        for turn in history
    ]

    for key in keys:
        try:
            client = genai.Client(api_key=key)
            chat = client.chats.create(
                model=summarizer._model_name(),
                config={"system_instruction": _SYSTEM_INSTRUCTION},
                history=seeded_history,
            )
            response = chat.send_message(message)
            text = (response.text or "").strip()
            if text:
                return text
        except Exception:
            continue
    return "응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
