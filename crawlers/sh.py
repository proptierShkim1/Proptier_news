"""
hana_p — SH(서울주택도시공사) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

_BASE_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139"
_LIST_URL = f"{_BASE_URL}/list.do"
_VIEW_URL = f"{_BASE_URL}/view.do"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MAX_PAGES = 50
# 목록의 상세보기 링크는 <a onclick="getDetailView('seq')"> 처럼 JS로만 이동한다
# (실제 href는 "#") — seq만 추출해 view.do에 대한 GET URL을 직접 구성한다.
_SEQ_RE = re.compile(r"getDetailView\('(\d+)'\)")


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """SH(서울주택도시공사) 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가
    전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL, params={"page": page}, headers=_HEADERS, timeout=_TIMEOUT
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [tr for tr in soup.select("table tr") if tr.select_one("a[onclick*=getDetailView]")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a[onclick*=getDetailView]")
                tds = tr.find_all("td")
                seq_match = _SEQ_RE.search(title_a.get("onclick", "")) if title_a else None
                if title_a is None or seq_match is None or len(tds) < 5:
                    continue
                announced_at = tds[3].get_text(strip=True)
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                try:
                    view_count = int(tds[4].get_text(strip=True))
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": f"{_VIEW_URL}?seq={seq_match.group(1)}&page=1",
                    "department": tds[2].get_text(strip=True),
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
