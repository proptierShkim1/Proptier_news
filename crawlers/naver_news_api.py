"""
hana_p — 네이버 공식 뉴스 검색 API 클라이언트. Client ID/Secret 필요(.env:
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET).
"""

import os
import re
from email.utils import parsedate_to_datetime

import requests

_API_URL = "https://openapi.naver.com/v1/search/news.json"
_TIMEOUT = 10
_DISPLAY = 100

_BOLD_TAG_RE = re.compile(r"</?b>")


def _clean(text: str) -> str:
    return _BOLD_TAG_RE.sub("", text).strip()


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


def search(term: str) -> list[dict]:
    resp = requests.get(
        _API_URL,
        params={"query": term, "display": _DISPLAY, "sort": "date"},
        headers=_auth_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()

    results = []
    for item in payload.get("items", []):
        url = item.get("originallink") or item.get("link", "")
        title = _clean(item.get("title", ""))
        if not url or not title:
            continue
        results.append({
            "source_detail": "뉴스",
            "title": title,
            "url": url,
            "snippet": _clean(item.get("description", "")),
            "posted_at": _format_posted_at(item.get("pubDate", "")),
        })
    return results
