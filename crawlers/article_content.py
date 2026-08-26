"""
hana_p — 네이버뉴스API가 originallink로 주는 뉴스 원문을 범용으로 추출한다. 원문 URL이
조선일보/매일경제/연합뉴스 등 언론사마다 제각각이라 사이트 전용 파서 대신, 흔히 쓰이는
본문 컨테이너 셀렉터들을 우선순위대로 시도하고 실패하면 <article> 태그로 폴백한다.
"""

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MIN_CONTENT_LENGTH = 80

_CONTENT_SELECTORS = [
    "#dic_area",
    "#articleBodyContents",
    "#article-view-content-div",
    "#articleBody",
    "#article_body",
    ".article_body",
    ".article-body",
    ".article_view",
    "div[itemprop='articleBody']",
    "article",
]


def fetch_content(url: str) -> str:
    """언론사 원문 페이지에서 본문 텍스트를 추출한다. 실패하거나 본문을 찾지 못하면
    빈 문자열을 반환한다."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        # resp.text는 서버가 Content-Type에 charset을 명시하지 않으면 requests가
        # ISO-8859-1로 잘못 간주해버려(RFC 2616 구버전 기본값) EUC-KR 등을 쓰는
        # 언론사 사이트에서 한글이 깨진다(모지바케) — resp.content(원본 바이트)를
        # BeautifulSoup에 넘기면 <meta charset> 태그를 직접 읽어 정확히 판별한다.
        soup = BeautifulSoup(resp.content, "html.parser")
        for selector in _CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if node is None:
                continue
            for junk in node.select("script, style"):
                junk.decompose()
            text = node.get_text("\n", strip=True)
            if len(text) >= _MIN_CONTENT_LENGTH:
                return text
        return ""
    except Exception:
        return ""
