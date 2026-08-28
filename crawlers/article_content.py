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

# 본문 컨테이너 안에 실제 기사 텍스트와 같이 섞여 나오는 사이트 UI 문구(글자크기 조절,
# 공유하기, 구독 버튼 등) — 108건 실측(2026-08-28, seoul.co.kr/fnnews.com/kyeonggi.com 등
# 7개 사이트)으로 확인된 패턴만 담는다. 줄 전체가 정확히 일치할 때만 걸러서, 실제 문장
# 안에 우연히 같은 문구가 들어있는 경우(예: "기사 읽어주기 기능을 써봤다")까지 지우지
# 않는다.
_BOILERPLATE_LINES = {
    "기사 읽어주기", "다시듣기", "다시 듣기", "글씨 크기 조절", "글자크기 설정", "글자크기",
    "글자크기 설정 시 다른 기사의 본문도", "동일하게 적용 됩니다.", "닫기", "프린트",
    "공유하기", "공유", "페이스북", "네이버블로그", "엑스", "카카오톡", "밴드", "네이버밴드",
    "X (트위터)", "URL 복사", "URL복사", "댓글", "이미지 확대", "이미지 확대 보기",
    "구독", "구독하기", "AI 요약", "close", "✕", "기자페이지", "가",
    "구글 검색에서 경기일보 기사를", "우선적으로 보여줍니다.",
}


def _is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in _BOILERPLATE_LINES:
        return True
    if stripped.startswith("구글에서 ") and stripped.endswith("먼저 보기"):
        return True
    if stripped.startswith(("http://", "https://")):
        return True
    return stripped.isdigit()


def _strip_boilerplate(text: str) -> str:
    lines = [ln.strip() for ln in text.split("\n") if not _is_boilerplate_line(ln)]
    return "\n".join(lines).strip()


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
            text = _strip_boilerplate(node.get_text("\n", strip=True))
            if len(text) >= _MIN_CONTENT_LENGTH:
                return text
        return ""
    except Exception:
        return ""
