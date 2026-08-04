"""
hana_p — 네이버 공식 뉴스 검색 API 클라이언트. Client ID/Secret 필요(.env:
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET).
"""

import html
import os
import re
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

_API_URL = "https://openapi.naver.com/v1/search/news.json"
_TIMEOUT = 10
_DISPLAY = 100
_MAX_START = 1000
_PAGE_DELAY_SECONDS = 0.5

_BOLD_TAG_RE = re.compile(r"</?b>")


def _clean(text: str) -> str:
    return html.unescape(_BOLD_TAG_RE.sub("", text)).strip()


def _auth_headers() -> dict:
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "NAVER_CLIENT_ID/NAVER_CLIENT_SECRET이 설정되지 않았습니다 (.env 확인)."
        )
    return {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}


def _format_posted_at(pub_date: str) -> str:
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y.%m.%d")
    except (TypeError, ValueError):
        return ""


def _within_days(posted_at: str, days: int) -> bool:
    """posted_at("YYYY.MM.DD")가 오늘 기준 days일 이내인지 여부. 형식이 다르거나
    비어 있으면(파싱 실패 등) 걸러내지 않고 항상 통과시킨다."""
    if not posted_at:
        return True
    try:
        dt = datetime.strptime(posted_at, "%Y.%m.%d")
    except ValueError:
        return True
    return (datetime.now().date() - dt.date()) <= timedelta(days=days)


def search(term: str, max_pages: int = 1, recency_days: int | None = None) -> list[dict]:
    """네이버 뉴스를 검색한다. max_pages=1(기본)이면 기존과 동일한 단일 호출.
    max_pages>1이면 API의 start 파라미터로 다음 페이지를 이어서 가져오고,
    recency_days가 주어지면 그보다 오래된 기사를 만나는 페이지에서 멈춘다
    (sort=date로 최신순 정렬이라, 한 페이지 안에서 기준을 벗어난 기사가
    보이면 그 뒤로는 더 오래된 기사만 남으므로 그 즉시 중단해도 안전하다)."""
    results = []
    for page in range(max_pages):
        start = page * _DISPLAY + 1
        if start > _MAX_START:
            break
        resp = requests.get(
            _API_URL,
            params={"query": term, "display": _DISPLAY, "start": start, "sort": "date"},
            headers=_auth_headers(),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items", [])
        if not items:
            break

        hit_cutoff = False
        for item in items:
            url = item.get("originallink") or item.get("link", "")
            title = _clean(item.get("title", ""))
            if not url or not title:
                continue
            posted_at = _format_posted_at(item.get("pubDate", ""))
            if recency_days is not None and not _within_days(posted_at, recency_days):
                hit_cutoff = True
                break
            results.append({
                "source_detail": "뉴스",
                "title": title,
                "url": url,
                "snippet": _clean(item.get("description", "")),
                "posted_at": posted_at,
            })

        if hit_cutoff or len(items) < _DISPLAY:
            break
        if page < max_pages - 1:
            time.sleep(_PAGE_DELAY_SECONDS)
    return results
