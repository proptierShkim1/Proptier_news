"""
hana_p — 서울시 정보소통광장 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://opengov.seoul.go.kr/press/list"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MAX_PAGES = 50
# 서울시 보도자료는 시정 전반(교육/문화/복지 등)을 다루므로, 부동산/주택 정책과 무관한
# 부서 게시물이 대부분이다 — 부서명에 이 키워드 중 하나라도 포함된 게시물만 남긴다.
# "도시"만 넣으면 "도시외교", "도시브랜드" 등 무관한 부서까지 걸려 "도시공간본부"처럼
# 더 구체적인 형태로 좁혔다 — 다른 부동산 관련 부서가 나타나면 추가할 것.
_RELEVANT_DEPT_KEYWORDS = ["주택", "도시공간본부", "정비", "재건축", "재개발", "건축"]


def _is_relevant_department(department: str) -> bool:
    return any(kw in department for kw in _RELEVANT_DEPT_KEYWORDS)


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """서울시 정보소통광장 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 주택/도시계획 관련 부서 게시물만 남기고 나머지 시정 전반 게시물은 걸러낸다.
    네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체
    수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL,
                params={"page": page, "items_per_page": 50},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            rows = [tr for tr in rows if tr.select_one("td.data-title a")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("td.data-title a")
                date_td = tr.select_one("td.data-date")
                dept_td = tr.select_one("td.data-dept")
                if title_a is None or date_td is None:
                    continue
                announced_at = date_td.get_text(strip=True)
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                department = dept_td.get_text(strip=True) if dept_td else ""
                if not _is_relevant_department(department):
                    continue
                hit_td = tr.select_one("td.data-hit")
                try:
                    view_count = int(hit_td.get_text(strip=True)) if hit_td else 0
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": urljoin(_LIST_URL, title_a["href"]),
                    "department": department,
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
