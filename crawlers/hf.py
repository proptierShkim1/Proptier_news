"""
hana_p — 한국주택금융공사(HF) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_PAGE_SIZE = 10
_MAX_PAGES = 50
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VIEW_COUNT_RE = re.compile(r"조회수\s*(\d+)")


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """HF 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의
    실패가 전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_SIZE
            resp = requests.get(
                _LIST_URL,
                params={"mode": "list", "article.offset": offset, "articleLimit": _PAGE_SIZE},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table.board-table tr")
            rows = [tr for tr in rows if tr.select_one("a[data-article-no]")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a[data-article-no]")
                row_text = tr.get_text(" ", strip=True)
                date_match = _DATE_RE.search(row_text)
                if title_a is None or date_match is None:
                    continue
                announced_at = date_match.group()
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                view_match = _VIEW_COUNT_RE.search(row_text)
                view_count = int(view_match.group(1)) if view_match else 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": urljoin(_LIST_URL, title_a["href"]),
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
