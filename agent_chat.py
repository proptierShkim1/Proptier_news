"""
hana_p — "AI AGENT" 페이지용 범용 Gemini 대화. summarizer.py와 같은 자격증명(GEMINI_API_KEYS/
GEMINI_MODEL)을 재사용한다.

매 메시지마다 새 genai.Client()로 대화를 재구성한다(이전 히스토리를 seed로 주입) — Streamlit
재실행이 다른 스레드에서 스크립트를 돌릴 수 있어, SDK의 chat 세션 객체를 session_state에
그대로 들고 있다가 재사용하면 내부 HTTP 클라이언트가 닫힌 상태로 남아 "client has been closed"
오류가 나는 걸 실제로 확인했다. 그래서 히스토리는 순수 텍스트로만 들고 있다가, 메시지를 보낼
때마다 새 세션에 주입하는 방식으로 바꿨다 — 여러 키로 failover하기도 이 방식이 더 쉽다.

벡터 검색(vectorizer.search_similar_mentions/search_similar_policy_events)으로 찾은 관련
뉴스·정책 자료는 build_grounding_context()로 텍스트 블록을 만들어 ask()의 context 인자로
주입한다 — 대화 히스토리(화면에 보이는 텍스트)에는 섞이지 않고, 그 턴의 system_instruction에만
추가되므로 매 질문마다 다른 검색 결과를 반영할 수 있다.
"""

from google import genai
from google.genai import types

import summarizer

_BASE_SYSTEM_INSTRUCTION = (
    "너는 프롭티어(부동산 AI 프롭테크 기업) 사내에서 쓰는 어시스턴트야. 한국어로 "
    "친근하고 간결하게 답변해."
)
_NO_CONTEXT_NOTE = (
    " 이 질문과 관련된 사내 뉴스·정책 데이터를 찾지 못했으니, 일반적인 지식으로 답하되 "
    "사내 데이터 기반 답변은 아니라는 점을 밝혀줘."
)
_WITH_CONTEXT_NOTE = (
    "\n\n다음은 이 질문과 관련해 사내에서 수집한 뉴스·정책 자료야. 이 자료를 우선 참고해서 "
    "답변하고, 자료에 없는 내용은 지어내지 마. 필요하면 어떤 자료를 참고했는지 간단히 언급해도 돼:\n\n"
)


def has_api_keys() -> bool:
    return bool(summarizer._load_api_keys())


def build_grounding_context(mention_hits: list[dict], policy_hits: list[dict]) -> str:
    """벡터 검색으로 찾은 관련 뉴스/정책 항목을 ask()에 넘길 텍스트 블록으로 만든다.
    둘 다 비어있으면 빈 문자열을 반환한다."""
    lines = []
    for m in mention_hits:
        header = f"- [뉴스] {m.get('title', '')} ({m.get('brand', '')} · {m.get('posted_at') or m.get('collected_at', '')})"
        lines.append(header)
        gist = (m.get("summary") or m.get("content") or m.get("snippet") or "").strip()
        if gist:
            lines.append(f"  {gist[:300]}")
    for p in policy_hits:
        lines.append(f"- [정책] {p.get('title', '')} ({p.get('source', '')} · {p.get('announced_at', '')})")
    return "\n".join(lines)


def ask(history: list[dict], message: str, context: str = "") -> str:
    """history는 이번 메시지를 제외한 이전 턴들 [{"role": "user"|"assistant", "content": str}, ...].
    context가 있으면 이번 턴의 system_instruction에 참고 자료로 덧붙인다(build_grounding_context
    결과). 매번 새 Client/chat 세션을 만들어 history를 주입한 뒤 message를 보내고 응답 텍스트를
    반환한다. 키가 없거나 모든 키 호출이 실패해도 예외를 던지지 않고 에러 메시지 문자열을 반환한다."""
    keys = summarizer._load_api_keys()
    if not keys:
        return "GEMINI_API_KEYS가 설정되지 않아 에이전트를 사용할 수 없습니다."

    system_instruction = _BASE_SYSTEM_INSTRUCTION
    system_instruction += _WITH_CONTEXT_NOTE + context if context else _NO_CONTEXT_NOTE

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
                config={"system_instruction": system_instruction},
                history=seeded_history,
            )
            response = chat.send_message(message)
            text = (response.text or "").strip()
            if text:
                return text
        except Exception:
            continue
    return "응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
