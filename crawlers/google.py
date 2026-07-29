"""
hana_p — Google 뉴스 RSS 검색 피드 파서. API 키 불필요.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_RECENCY_WINDOW_DAYS = 7


def _is_recent(pub_date: str, now: datetime) -> bool:
    """pub_date가 now 기준 최근 _RECENCY_WINDOW_DAYS일 이내인지 여부.
    날짜를 파싱할 수 없으면(형식 변경 등) 걸러내지 않고 항상 통과시킨다."""
    try:
        dt = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return now - dt <= timedelta(days=_RECENCY_WINDOW_DAYS)


def _parse(xml_text: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(xml_text)
    results = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue
        pub_date = (item.findtext("pubDate") or "").strip()
        if not _is_recent(pub_date, now):
            continue
        results.append({
            "source_detail": "뉴스",
            "title": title,
            "url": url,
            "snippet": title,
            "posted_at": pub_date,
        })
    return results


def search(term: str) -> list[dict]:
    resp = requests.get(
        "https://news.google.com/rss/search",
        params={"q": term, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse(resp.text)
