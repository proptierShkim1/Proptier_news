"""
hana_p — 네이버 통합검색(블로그/카페) 스크래퍼. API 키 불필요.
"""

import re
from datetime import datetime
from urllib.parse import urljoin

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
_MIN_TEXT_LEN = 10
_SUFFIX_RE = re.compile(r"새 창 열림\s*$")

_URL_PATTERNS = {
    "블로그": re.compile(r"^https://blog\.naver\.com/[^/]+/\d+"),
    "카페": re.compile(r"^https://cafe\.naver\.com/[^/?]+/\d+"),
}

_DATE_CAPTION_RE = re.compile(r"^\d+(분|시간|일)\s*전$|^\d{4}\.\d{2}\.\d{2}\.?$")
_MAX_ANCESTOR_DEPTH = 12


def _clean(text: str) -> str:
    return _SUFFIX_RE.sub("", text).strip()


def _find_posted_at(anchor) -> str:
    """제목 링크(anchor)에서 부모로 계속 올라가며, 그 조상이 포함하는 결과-글 링크가
    정확히 1개(자기 자신)인 동안만 계속 올라가고, 그 범위 안에서 날짜/상대시각 캡션을
    찾으면 반환한다."""
    node = anchor
    for _ in range(_MAX_ANCESTOR_DEPTH):
        node = node.parent
        if node is None or not hasattr(node, "select"):
            break
        post_links = {
            a["href"].split("?")[0]
            for a in node.select("a[href]")
            if any(p.match(a["href"].split("?")[0]) for p in _URL_PATTERNS.values())
        }
        if len(post_links) > 1:
            break
        for el in node.find_all(["span", "div"]):
            text = el.get_text(strip=True)
            if _DATE_CAPTION_RE.match(text):
                return text
    return ""


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    texts_by_url: dict[str, list[str]] = {}
    detail_by_url: dict[str, str] = {}
    posted_at_by_url: dict[str, str] = {}

    for source_detail, pattern in _URL_PATTERNS.items():
        for a in soup.select("a[href]"):
            href = a["href"].split("?")[0]
            if not pattern.match(href):
                continue
            text = _clean(a.get_text(strip=True))
            if len(text) < _MIN_TEXT_LEN:
                continue
            texts_by_url.setdefault(href, []).append(text)
            detail_by_url[href] = source_detail
            if href not in posted_at_by_url:
                posted_at_by_url[href] = _find_posted_at(a)

    results = []
    for url, texts in texts_by_url.items():
        unique_texts = sorted(set(texts), key=len)
        results.append({
            "source_detail": detail_by_url[url],
            "title": unique_texts[0],
            "url": url,
            "snippet": unique_texts[-1],
            "posted_at": posted_at_by_url.get(url, ""),
        })
    return results


def search(term: str) -> list[dict]:
    resp = requests.get(
        "https://search.naver.com/search.naver",
        params={"query": term},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = _parse(resp.text)
    now = datetime.now()
    for record in results:
        resolved = resolve_relative_korean_date(record["posted_at"], now)
        if resolved is not None:
            record["posted_at"] = resolved
    return results


def fetch_content(url: str) -> str:
    """네이버 블로그 게시글 본문을 가져온다. 실패 시 전부 빈 문자열을 반환한다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        iframe = soup.select_one("iframe#mainFrame")
        if not iframe or not iframe.get("src"):
            return ""
        post_url = urljoin(url, iframe["src"])
        resp2 = requests.get(post_url, headers=_HEADERS, timeout=_TIMEOUT)
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        body = soup2.select_one("div.se-main-container")
        return body.get_text("\n", strip=True) if body else ""
    except Exception:
        return ""
