"""
hana_p — Gemini 기반 기사 원문 요약. MarketInsight/insights.py와 같은 방식(genai.Client,
GEMINI_API_KEYS 여러 키 순차 시도, GEMINI_MODEL로 모델 지정)을 그대로 따른다.

원문(content)이 실제로 수집된 기사만 대상으로 한다 — 제목/짧은 스니펫만 있는 기사를
요약하면 근거가 부족해 지어낸 내용이 섞일 위험이 있어서다.
"""

import hashlib
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")

_DEFAULT_MODEL = "gemini-2.5-flash"
SUMMARY_LEN = 300


def _load_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    random.shuffle(keys)
    return keys


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
    발췌)을 그대로 쓰므로 예외를 던지지 않는다. 호출마다 성공/실패와 토큰 사용량을
    api_usage_log에 남겨 설정 > API 사용량 탭에서 조회할 수 있게 한다."""
    import db

    content = (content or "").strip()
    keys = _load_api_keys()
    if not keys or not content:
        return ""

    prompt = _build_prompt(title, content)
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=_model_name(), contents=prompt)
            usage = response.usage_metadata
            db.insert_api_usage(
                "summarizer", _model_name(), ok=True,
                prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
                thoughts_tokens=(usage.thoughts_token_count or 0) if usage else 0,
                total_tokens=(usage.total_token_count or 0) if usage else 0,
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception:
            db.insert_api_usage("summarizer", _model_name(), ok=False)
            continue
    return ""


def ensure_pdf_summaries(items: list[dict]) -> bool:
    """PDF에 실제로 노출되는 상위 항목(top5)에 대해서만 AI 요약을 만들어 DB에 저장한다.
    이미 summary가 있고 그 summary를 만든 content와 지금 content가 같으면(content_hash
    일치) 다시 호출하지 않는다 — content_hash가 비어있으면(이 기능 도입 이전에 만들어진
    옛 summary) 굳이 재생성하지 않고 그대로 둔다(2026-08-28 이전 데이터를 한꺼번에
    재호출하는 비용을 피하기 위함). content가 나중에 바뀌었는데(예: 스크래퍼 개선) 옛
    content_hash가 남아있으면 재생성한다. views/report.py의 렌더링 경로와, scheduler.py의
    백그라운드 사전 생성 경로 양쪽에서 같은 로직을 쓴다 — 백그라운드에서 미리 돌려두면
    사용자가 PDF 보고서 페이지를 열 때 Gemini 호출을 기다리지 않는다."""
    import db

    updated = False
    for item in items:
        if not (item.get("content") and item.get("mention_id")):
            continue
        current_hash = _content_hash(item["content"])
        stale = item.get("content_hash") and item["content_hash"] != current_hash
        if item.get("summary") and not stale:
            continue
        ai_summary = summarize_article(item["title"], item["content"])
        if ai_summary:
            db.update_mention_summary(item["mention_id"], ai_summary, content_hash=current_hash)
            item["summary"] = ai_summary
            item["content_hash"] = current_hash
            item["desc_long"] = [ai_summary]
            updated = True
    return updated


def presummarize_top_pdf_items(limit: int = 5) -> int:
    """수집 스케줄과 무관하게 PDF 상위 항목의 AI 요약을 미리 만들어 둔다 (scheduler.py에서
    주기적으로 호출). 반환값은 새로 요약한 건수."""
    import db
    import news_feed

    mentions = db.get_mentions(limit=news_feed.RECENT_LIMIT, channels=news_feed.enabled_channels())
    if not mentions:
        return 0
    news_items = news_feed.build_news_items(mentions, news_feed.own_brand_names())
    top_items = news_items[:limit]
    before = {id(it): it.get("summary") for it in top_items}
    ensure_pdf_summaries(top_items)
    return sum(1 for it in top_items if it.get("summary") and it.get("summary") != before.get(id(it)))
