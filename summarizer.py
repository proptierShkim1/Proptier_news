"""
hana_p — Gemini 기반 기사 원문 요약. MarketInsight/insights.py와 같은 방식(genai.Client,
GEMINI_API_KEYS 여러 키 순차 시도, GEMINI_MODEL로 모델 지정)을 그대로 따른다.

원문(content)이 실제로 수집된 기사만 대상으로 한다 — 제목/짧은 스니펫만 있는 기사를
요약하면 근거가 부족해 지어낸 내용이 섞일 위험이 있어서다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")

_DEFAULT_MODEL = "gemini-2.5-flash"
SUMMARY_LEN = 400


def _load_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)


def _build_prompt(title: str, content: str) -> str:
    return (
        "다음은 부동산·프롭테크 관련 뉴스 기사 원문이야. 이 기사를 한국어로 "
        f"{SUMMARY_LEN}자 이내로 요약해줘. 핵심 내용만 자연스러운 문장으로 요약하고, "
        "글자 수를 맞추려고 문장을 중간에 끊지 마. 기사에 없는 내용은 지어내지 마.\n\n"
        f"제목: {title}\n\n본문:\n{content}"
    )


def summarize_article(title: str, content: str) -> str:
    """제목+원문을 Gemini로 요약해 반환한다. 키가 없거나 원문이 비었거나 모든 키 호출이
    실패하면 빈 문자열을 반환한다 — 호출부(collector.py)는 이 경우 기존 폴백(원문 일부
    발췌)을 그대로 쓰므로 예외를 던지지 않는다."""
    content = (content or "").strip()
    keys = _load_api_keys()
    if not keys or not content:
        return ""

    prompt = _build_prompt(title, content)
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=_model_name(), contents=prompt)
            text = (response.text or "").strip()
            if text:
                return text
        except Exception:
            continue
    return ""
