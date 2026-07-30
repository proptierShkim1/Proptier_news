"""
hana_p — 국토교통부 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """국토교통부 보도자료 목록을 start~end 날짜 범위로 한 번에 가져온다. 네트워크 오류나
    페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체 수집 과정을
    중단시키면 안 된다."""
    try:
        resp = requests.get(
            _LIST_URL,
            params={
                "psize": 100,
                "search_regdate_s": start.isoformat(),
                "search_regdate_e": end.isoformat(),
                "lcmspage": 1,
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.select_one("table.bd_tbl")
        if table is None:
            return []

        results = []
        for tr in table.select("tr"):
            tds = tr.select("td")
            if len(tds) != 5:
                continue
            link = tds[1].select_one("a")
            if link is None:
                continue
            title = link.get_text(strip=True)
            url = urljoin(_LIST_URL, link["href"])
            department = tds[2].get_text(strip=True)
            announced_at = tds[3].get_text(strip=True)
            try:
                view_count = int(tds[4].get_text(strip=True))
            except ValueError:
                view_count = 0
            results.append({
                "title": title,
                "url": url,
                "department": department,
                "announced_at": announced_at,
                "view_count": view_count,
            })
        return results
    except Exception:
        return []
