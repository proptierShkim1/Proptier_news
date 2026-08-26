"""
hana_p — Gemini API 요금 추정 공용 로직. views/settings.py(설정 > API 사용량 탭)와
agent_chat.py(AI AGENT의 "API 비용 얼마야" 지표 도구) 양쪽에서 같은 계산을 쓴다 —
전에는 두 파일에 동일한 상수·수식을 복붙해두고 "하나 바꾸면 다른 쪽도 갱신할 것"
이라는 주석으로만 동기화를 맡겼는데, vectorizer(임베딩) 단가까지 조건부로 추가되며
드리프트 위험이 커져 하나로 합쳤다.

가격은 2026-08 기준 Gemini API 공식 요금(ai.google.dev/gemini-api/docs/pricing,
Standard tier) — 실제 청구 금액과 다를 수 있다.
"""

PRICE_PER_1M_FLASH_INPUT_USD = 0.30
PRICE_PER_1M_FLASH_OUTPUT_USD = 2.50
PRICE_PER_1M_EMBEDDING_INPUT_USD = 0.15

# gemini-embedding-001 API 응답은 usage_metadata를 안 줘서 실제 토큰 수를 알 수 없다.
# 실제 기사 원문(한국어)으로 count_tokens API를 5건 표본 호출해 글자수/토큰수 비율을
# 실측한 값(1.26~1.42, 평균 1.38)을 반올림해 썼다 — 영어 기준 통념(4글자당 1토큰)을
# 그대로 쓰면 한국어 서브워드 분할 특성상 크게 틀린다.
CHARS_PER_TOKEN_ESTIMATE = 1.4


def estimate_tokens_from_text(text: str) -> int:
    """벡터화 API가 실제 토큰 수를 안 주는 텍스트에 대해 대략적인 토큰 수를 추정한다.
    정확한 청구 토큰 수가 아니라 근사치다."""
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN_ESTIMATE))


def estimate_cost_usd(feature: str, prompt_tokens: int, output_tokens: int) -> float:
    """feature별로 실제 호출하는 모델이 달라 단가도 다르다 — summarizer/agent_chat은
    gemini-2.5-flash(입력/출력 단가 분리), vectorizer는 gemini-embedding-001(입력
    단가만 존재, output_tokens는 항상 0)."""
    if feature == "vectorizer":
        return (prompt_tokens / 1_000_000) * PRICE_PER_1M_EMBEDDING_INPUT_USD
    return (
        (prompt_tokens / 1_000_000) * PRICE_PER_1M_FLASH_INPUT_USD
        + (output_tokens / 1_000_000) * PRICE_PER_1M_FLASH_OUTPUT_USD
    )
