"""
hana_p — LH(한국토지주택공사) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.lh.or.kr/gallery.es"
_MID = "a10502000000"
_BID = "0003"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 게시판이 오래된 글까지 무한히 이어지므로, start 날짜에 도달하면 멈추되 혹시 모를
# 무한 루프를 막기 위한 안전장치로 최대 페이지 수를 둔다.
_MAX_PAGES = 50
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LIST_NO_RE = re.compile(r"list_no=(\d+)")


def _parse_item(a) -> dict | None:
    title_el = a.select_one("strong.title")
    date_el = a.select_one("span.date")
    href = a.get("href", "")
    if title_el is None or date_el is None or not href:
        return None
    date_match = _DATE_RE.search(date_el.get_text(" ", strip=True))
    list_no_match = _LIST_NO_RE.search(href)
    if not date_match or not list_no_match:
        return None
    return {
        "title": title_el.get_text(strip=True),
        # href의 nPage/vlist_no_npage 등은 "현재 보고 있는 목록 페이지"를 반영해 조회할 때마다
        # 값이 달라진다 — list_no만으로 상세 URL을 직접 구성해야 같은 글이 항상 같은 URL이 되고,
        # DB의 URL UNIQUE 제약으로 정상적으로 중복 방지된다 (nPage를 그대로 쓰면 페이지마다
        # URL이 달라져 같은 글이 중복 저장됨 — 실제로 프로덕션 DB에서 확인된 버그).
        "url": f"{_LIST_URL}?mid={_MID}&bid={_BID}&act=view&list_no={list_no_match.group(1)}",
        "announced_at": date_match.group(),
    }


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """LH 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 맨 위 'blog_box' 특집 항목은 페이지마다 반복 노출되고 정렬 순서를 따르지
    않으므로, 이 항목 때문에 페이지네이션이 조기 중단되지 않도록 따로 취급한다.
    네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가
    전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        seen_urls = set()
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL,
                params={"mid": _MID, "bid": _BID, "nPage": page},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            featured_a = soup.select_one(".blog_box a")
            list_as = soup.select(".board_list .gallery_list li a")
            if featured_a is None and not list_as:
                break

            reached_start = False
            for a, is_featured in [(featured_a, True)] + [(x, False) for x in list_as]:
                if a is None:
                    continue
                item = _parse_item(a)
                if item is None or item["url"] in seen_urls:
                    continue
                if item["announced_at"] < start.isoformat():
                    if is_featured:
                        continue
                    reached_start = True
                    break
                if item["announced_at"] > end.isoformat():
                    continue
                seen_urls.add(item["url"])
                results.append({
                    "title": item["title"],
                    "url": item["url"],
                    "department": "",
                    "announced_at": item["announced_at"],
                    "view_count": 0,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
