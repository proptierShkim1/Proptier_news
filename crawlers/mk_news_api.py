"""
hana_p — 매일경제(매경 AI) 뉴스 검색 API 클라이언트. IP 화이트리스트 인증이라
별도 키가 필요 없다(사전에 요청 서버 IP를 매경 쪽에 등록해 둬야 함).
"""

import re
import time
from datetime import date, datetime, timedelta

import requests

_API_URL = "https://api.mk-agents.com/search/vector/filtered"
_TIMEOUT = 10
_LIMIT = 20
_BACKFILL_LIMIT = 100
_MEDIA_CODES = ["82"]  # 매일경제만 검색 (스펙상 현재 82만 유효)
_CHUNK_DELAY_SECONDS = 0.5

_SUMMARY_RE = re.compile(r"\[SUMMARY\](.*?)(?=\[BODY\]|$)", re.S)
_BODY_RE = re.compile(r"\[BODY\](.*)", re.S)


def _extract_tag(pattern: "re.Pattern", text: str) -> str:
    m = pattern.search(text or "")
    return m.group(1).strip() if m else ""


def _format_posted_at(date_str: str) -> str:
    try:
        return datetime.fromisoformat(date_str).strftime("%Y.%m.%d")
    except (TypeError, ValueError):
        return ""


def _request(term: str, limit: int, date_from: str | None, date_end: str | None) -> list[dict]:
    body = {"query": term, "limit": limit, "filters": {"media_codes": _MEDIA_CODES}}
    if date_from:
        body["date_from"] = date_from
    if date_end:
        body["date_end"] = date_end
    resp = requests.post(
        _API_URL, json=body, headers={"Content-Type": "application/json"}, timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()

    results = []
    for item in payload.get("results", []):
        title = (item.get("title") or "").strip()
        art_id = item.get("art_id")
        if not title or not art_id:
            continue
        text = item.get("text", "")
        summary = _extract_tag(_SUMMARY_RE, text) or (item.get("subtitle") or "").strip()
        # 매경 API는 별도 인증키 없이 IP 화이트리스트로 접근하며 원문 URL 패턴이
        # 스펙에 명시되어 있지 않아(요청에 따라 URL 없이 처리), art_id 기반의
        # 내부 식별자만 mentions.url(UNIQUE) 제약을 만족시키는 용도로 사용한다.
        results.append({
            "source_detail": "매경뉴스",
            "title": title,
            "url": f"mk-api:{art_id}",
            "snippet": summary,
            "posted_at": _format_posted_at(item.get("date", "")),
            "content": _extract_tag(_BODY_RE, text),
        })
    return results


def _date_windows(days: int, chunks: int) -> list:
    """오늘부터 days일 전까지의 구간을 chunks개 이하로 쪼갠 (date_from, date_end)
    목록을 최신 구간부터 반환한다. API가 offset 파라미터를 지원하지 않아 진짜
    페이지네이션이 불가능하므로, 날짜 구간을 나눠 반복 호출하는 방식으로 대신한다."""
    chunks = max(1, chunks)
    chunk_size = max(1, -(-days // chunks))  # ceil division
    windows = []
    end = date.today()
    remaining = days
    while remaining > 0 and len(windows) < chunks:
        span = min(chunk_size, remaining)
        start = end - timedelta(days=span - 1)
        windows.append((start.isoformat(), end.isoformat()))
        end = start - timedelta(days=1)
        remaining -= span
    return windows


def search(term: str, max_pages: int = 1, recency_days: int | None = None) -> list[dict]:
    """매경 뉴스 검색 API를 호출한다. recency_days가 없으면(정기 수집) 기간 제한 없이
    limit개만 한 번 호출한다. recency_days가 주어지면(백필) 그 기간을 max_pages개
    구간으로 쪼개 구간별로 호출해 결과를 모은다."""
    if recency_days is None:
        return _request(term, _LIMIT, None, None)

    results = []
    windows = _date_windows(recency_days, max_pages)
    for i, (date_from, date_end) in enumerate(windows):
        results.extend(_request(term, _BACKFILL_LIMIT, date_from, date_end))
        if i < len(windows) - 1:
            time.sleep(_CHUNK_DELAY_SECONDS)
    return results
