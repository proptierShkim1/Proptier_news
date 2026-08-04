"""
hana_p — 다음(Daum) 뉴스 검색 스크래퍼. API 키 불필요.
뉴스 검색(w=news)만 대상으로 하며, p(페이지) 파라미터로 최대 _MAX_PAGES까지 순회한다.
"""

import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from utils import resolve_relative_korean_date

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MAX_PAGES = 10
_PAGE_DELAY_SECONDS = 1
_RECENCY_WINDOW_DAYS = 7

_RELATIVE_RE = re.compile(r"^(\d+)(분|시간|일)\s*전$")
_RELATIVE_UNIT_TO_KWARG = {"분": "minutes", "시간": "hours", "일": "days"}


def _is_recent(posted_at: str, now: datetime, recency_days: int = _RECENCY_WINDOW_DAYS) -> bool:
    """posted_at(YYYY.MM.DD 또는 "N분/시간/일 전")가 now 기준 최근
    recency_days일 이내인지 여부. 형식이 다르거나 비어 있으면 항상 통과시킨다."""
    if not posted_at:
        return True

    relative = _RELATIVE_RE.match(posted_at)
    if relative:
        amount, unit = relative.groups()
        age = timedelta(**{_RELATIVE_UNIT_TO_KWARG[unit]: int(amount)})
        return age <= timedelta(days=recency_days)

    try:
        dt = datetime.strptime(posted_at, "%Y.%m.%d")
    except ValueError:
        return True
    return now.date() - dt.date() <= timedelta(days=recency_days)


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li[data-docid]"):
        title_a = li.select_one(".item-title a")
        if not title_a:
            continue
        url = title_a.get("href", "").strip()
        title = title_a.get_text(strip=True)
        if not url or not title:
            continue
        desc_a = li.select_one(".conts-desc a")
        snippet = desc_a.get_text(strip=True) if desc_a else title
        date_span = li.select_one(".gem-subinfo .txt_info")
        posted_at = date_span.get_text(strip=True) if date_span else ""
        results.append({
            "source_detail": "뉴스",
            "title": title,
            "url": url,
            "snippet": snippet,
            "posted_at": posted_at,
        })
    return results


def search(term: str, recency_days: int = _RECENCY_WINDOW_DAYS, max_pages: int = _MAX_PAGES) -> list[dict]:
    now = datetime.now()
    results = []
    seen_urls = set()
    for page in range(1, max_pages + 1):
        resp = requests.get(
            "https://search.daum.net/search",
            params={"w": "news", "q": term, "p": page},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        page_results = _parse(resp.text)
        if not page_results:
            break

        new_count = 0
        for record in page_results:
            if record["url"] in seen_urls:
                continue
            seen_urls.add(record["url"])
            new_count += 1
            resolved = resolve_relative_korean_date(record["posted_at"], now)
            if resolved is not None:
                record["posted_at"] = resolved
            if _is_recent(record["posted_at"], now, recency_days):
                results.append(record)
        if new_count == 0:
            break

        if page < max_pages:
            time.sleep(_PAGE_DELAY_SECONDS)
    return results


def fetch_content(url: str) -> str:
    """다음 뉴스(v.daum.net) 기사 본문을 가져온다. 실패 시 전부 빈 문자열을 반환한다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.select_one("div.article_view")
        return body.get_text("\n", strip=True) if body else ""
    except Exception:
        return ""
