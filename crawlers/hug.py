"""
hana_p — 주택도시보증공사(HUG) 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000001.jsp"
_DETAIL_URL = "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000002.jsp"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 이 게시판은 페이지 전환이 아니라 "rowSize"만큼 누적해서 더 보여주는 방식이라
# (POST할 때마다 처음부터 rowSize개를 다시 돌려줌), 매번 응답 전체를 다시 받아
# 이전에 처리한 개수 이후의 새 행만 처리한다.
_ROW_STEP = 20
_MAX_ROWS = 500
_NEW_BADGE = "최근 게시물"


def _to_iso_date(raw: str) -> str:
    """'2026.07.27' 형식을 '2026-07-27'로 변환한다."""
    parts = [p for p in raw.strip().split(".") if p]
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """HUG 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, rowSize를 늘려가며 새로 나타난 행 중 start보다
    오래된 글을 만나면 멈춘다. 응답은 EUC-KR로 인코딩되어 있다. 네트워크 오류나
    페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체 수집 과정을
    중단시키면 안 된다."""
    try:
        results = []
        prev_count = 0
        row_size = _ROW_STEP
        while row_size <= _MAX_ROWS:
            resp = requests.post(
                _LIST_URL,
                data={"rowSize": row_size, "searchCondition": "01", "searchKeyword": ""},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [tr for tr in soup.select("table.tbl-style02 tr") if tr.select_one("a[href]")]
            if len(rows) <= prev_count:
                break
            new_rows = rows[prev_count:]
            prev_count = len(rows)

            reached_start = False
            for tr in new_rows:
                a = tr.select_one("a[href]")
                tds = tr.find_all("td")
                if a is None or not tds:
                    continue
                announced_at = _to_iso_date(tds[-1].get_text(strip=True))
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                title = a.get_text(strip=True)
                if title.startswith(_NEW_BADGE):
                    title = title[len(_NEW_BADGE):].strip()
                idx = a["href"].split("idx=")[-1]
                results.append({
                    "title": title,
                    "url": f"{_DETAIL_URL}?idx={idx}",
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": 0,
                })
            if reached_start:
                break
            row_size += _ROW_STEP
        return results
    except Exception:
        return []
