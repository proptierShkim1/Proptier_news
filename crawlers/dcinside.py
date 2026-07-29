"""
hana_p — 디시인사이드 통합검색 스크래퍼. API 키 불필요.
"""

from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select(".sch_result_list li"):
        title_a = li.select_one("a.tit_txt")
        if not title_a:
            continue
        url = title_a.get("href", "").strip()
        title = title_a.get_text(strip=True)
        if not url or not title:
            continue

        snippet_p = next(
            (p for p in li.select("p.link_dsc_txt") if "dsc_sub" not in p.get("class", [])),
            None,
        )
        snippet = snippet_p.get_text(strip=True) if snippet_p else title

        gallery_a = li.select_one("p.link_dsc_txt.dsc_sub a.sub_txt")
        if gallery_a:
            gallery = gallery_a.get_text(strip=True)
            snippet = f"[{gallery}] {snippet}"

        date_span = li.select_one(".dsc_sub .date_time")
        posted_at = date_span.get_text(strip=True) if date_span else ""

        results.append({
            "source_detail": "갤러리",
            "title": title,
            "url": url,
            "snippet": snippet,
            "posted_at": posted_at,
        })
    return results


def search(term: str) -> list[dict]:
    resp = requests.get(
        f"https://search.dcinside.com/combine/q/{quote(term, safe='')}",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse(resp.text)


def fetch_content(url: str) -> str:
    """게시글 상세 페이지에서 본문 텍스트를 가져온다. 실패 시 전부 빈 문자열을 반환한다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.select_one("div.write_div")
        return body.get_text("\n", strip=True) if body else ""
    except Exception:
        return ""
