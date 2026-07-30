"""
hana_p — 한국부동산원(REB) 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.reb.or.kr/reb/na/ntt/selectNttList.do"
_DETAIL_URL = "https://www.reb.or.kr/reb/na/ntt/selectNttInfo.do"
_MI = "9565"
_BBS_ID = "1154"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 게시판 페이지가 오래된 글까지 무한히 이어지므로, start 날짜에 도달하면 멈추되
# 혹시 모를 무한 루프를 막기 위한 안전장치로 최대 페이지 수를 둔다.
_MAX_PAGES = 50


def _to_iso_date(raw: str) -> str:
    """'2026.07.27.' 형식을 '2026-07-27'로 변환한다."""
    parts = [p for p in raw.strip().rstrip(".").split(".") if p]
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _fetch_page(page: int) -> str:
    resp = requests.post(
        _LIST_URL,
        data={
            "currPage": page,
            "listUseAt": "Y", "replyAt": "N", "cvplAt": "N", "nttCnChk": "N",
            "sysId": "reb", "mberId": "", "bbsTy": "CUSTOM", "customId": "NesDta",
            "resveInsertAt": "N", "newHour": "24", "cmmnCode": "ctgryBbs1105",
            "replyDtAt": "N", "maxSn": "10", "noticeAt": "N", "nttOrdr": "regdt",
            "answerTy": "N", "mi": _MI, "useAt": "Y", "minSn": "0",
            "bbsId": _BBS_ID, "ctgryBbs": "Y", "readyNttMber": "Y",
        },
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """한국부동산원 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을
    만나면 멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 —
    이 함수의 실패가 전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            soup = BeautifulSoup(_fetch_page(page), "html.parser")
            rows = soup.select("table tbody tr")
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a.nttInfoBtn")
                tds = tr.find_all("td")
                if title_a is None or len(tds) < 4:
                    continue
                ntt_sn = title_a.get("data-id", "")
                title = title_a.get_text(strip=True)
                announced_at = _to_iso_date(tds[2].get_text(strip=True))
                if not ntt_sn or not title or not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                try:
                    view_count = int(tds[3].get_text(strip=True))
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title,
                    "url": f"{_DETAIL_URL}?mi={_MI}&bbsId={_BBS_ID}&nttSn={ntt_sn}",
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
