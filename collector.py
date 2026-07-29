"""
hana_p — 키워드 x 채널별 크롤러 실행, 저장, 실행이력 기록 조율.
"""

import re
import threading
import time
import uuid
from datetime import datetime

import db
from crawlers import daum as daum_crawler
from crawlers import dcinside as dcinside_crawler
from crawlers import google as google_crawler
from crawlers import naver as naver_crawler
from utils import load_keywords

_CRAWLERS = {
    "네이버": naver_crawler.search,
    "구글": google_crawler.search,
    "다음": daum_crawler.search,
    "커뮤니티": dcinside_crawler.search,
}

_CONTENT_FETCHERS = {
    "커뮤니티": lambda record: dcinside_crawler.fetch_content(record["url"]),
    "네이버": lambda record: (
        naver_crawler.fetch_content(record["url"]) if record["source_detail"] == "블로그" else ""
    ),
    "다음": lambda record: daum_crawler.fetch_content(record["url"]),
}

# 키워드가 일반 단어와 겹치는 경우를 걸러내기 위한 기본 문맥 단어 목록 (부동산 도메인)
_REAL_ESTATE_CONTEXT_WORDS = [
    "부동산", "아파트", "주택", "오피스텔", "빌라", "상가", "토지", "건물",
    "전세", "월세", "매매", "매물", "시세", "실거래가", "호가", "임대", "임차",
    "분양", "청약", "입주", "재건축", "재개발", "리모델링",
    "중개", "공인중개사", "중개사", "등기", "등기부등본",
    "전세사기", "전세보증금", "전세자금대출", "주택담보대출", "임대차", "임대차계약",
    "확정일자", "전세권", "갭투자", "역전세",
    "국토교통부", "국토부", "한국토지주택공사", "LH",
    "집값", "매매가", "부동산시장", "부동산 시장", "부동산 정책", "부동산 규제", "부동산 대책",
    "조정대상지역", "투기과열지구", "토지거래허가구역",
    "세입자", "임차인", "임대인", "집주인",
    "신축", "구축", "준공", "원룸", "투룸",
    "AI", "인공지능", "프롭테크", "프롭티어",
]
_REQUEST_DELAY_SECONDS = 2
_CONTENT_FETCH_DELAY_SECONDS = 1

_state_lock = threading.Lock()
_active_run_id: str | None = None

_HANGUL = re.compile(r"[가-힣]")
_PARTICLES = sorted([
    "은", "는", "이", "가", "을", "를", "에", "에서", "에게", "께",
    "으로", "로", "와", "과", "도", "만", "의", "나", "라", "이나", "이라",
    "부터", "까지", "처럼", "만큼", "밖에",
], key=len, reverse=True)


def _is_noise_by_boundary(term: str, text: str) -> bool:
    """term이 text에서 매번 앞에 다른 한글 음절이 붙어 있거나, 뒤에 공백/조사/문자열
    끝이 아닌 것이 바로 붙어 있는 채로만 등장하면 합성어 노이즈로 보고 True를 반환한다."""
    start = 0
    found_any = False
    while True:
        idx = text.find(term, start)
        if idx == -1:
            return found_any
        found_any = True
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(term):]
        before_ok = not _HANGUL.match(before)
        after_ok = (
            not after
            or after[0] == " "
            or any(after.startswith(p) for p in _PARTICLES)
        )
        if before_ok and after_ok:
            return False
        start = idx + 1


def _search_terms(brand_entry: dict) -> list:
    return [brand_entry["name"]]


def _is_excluded(record: dict, exclude_terms: list) -> bool:
    if not exclude_terms:
        return False
    text = f"{record.get('title', '')} {record.get('snippet', '')}".lower()
    return any(term.lower() in text for term in exclude_terms)


def _is_missing_required_context(context_words: list, text: str) -> bool:
    if not context_words:
        return False
    return not any(word in text for word in context_words)


def active_run_id() -> str | None:
    with _state_lock:
        return _active_run_id


def start_background_collection(trigger: str = "수동") -> str | None:
    """이미 진행 중인 백그라운드 수집이 없으면 데몬 스레드로 수집을 시작하고 run_id를 반환한다."""
    global _active_run_id
    with _state_lock:
        if _active_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_run_id = run_id

    def _worker():
        global _active_run_id
        try:
            run_collection(trigger=trigger, run_id=run_id)
        finally:
            with _state_lock:
                _active_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id


def run_collection(
    trigger: str = "수동", on_progress=None, run_id: str | None = None
) -> list[dict]:
    """등록된 모든 키워드 x 채널 조합을 수집. 조합별 run_logs 항목 리스트 반환."""
    cfg = load_keywords()
    context_words = cfg.get("context") or []
    exclude_terms = cfg.get("exclude") or []
    run_id = run_id or str(uuid.uuid4())[:8]
    log_entries = []
    for brand_entry in cfg["brands"]:
        for channel, crawl in _CRAWLERS.items():
            entry = _collect_one(
                brand_entry, channel, crawl, trigger, run_id, context_words, exclude_terms
            )
            log_entries.append(entry)
            if on_progress is not None:
                on_progress(entry)
            time.sleep(_REQUEST_DELAY_SECONDS)
    return log_entries


def _collect_one(
    brand_entry: dict, channel: str, crawl, trigger: str, run_id: str,
    context_words: list, exclude_terms: list,
) -> dict:
    brand_name = brand_entry["name"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "ran_at": now, "trigger": trigger, "brand": brand_name, "channel": channel,
        "fetched": 0, "inserted": 0, "skipped": 0, "ok": 1, "message": "", "run_id": run_id,
    }

    term_errors = []
    ok_terms = 0
    for term in _search_terms(brand_entry):
        try:
            records = crawl(term)
        except Exception as e:
            term_errors.append(f"{term}: {e}")
            continue
        ok_terms += 1
        entry["fetched"] += len(records)
        for record in records:
            text = f"{record.get('title', '')} {record.get('snippet', '')}"
            if term not in text:
                entry["skipped"] += 1
                continue
            if _is_noise_by_boundary(term, text):
                entry["skipped"] += 1
                continue
            if _is_missing_required_context(context_words, text):
                entry["skipped"] += 1
                continue
            if _is_excluded(record, exclude_terms):
                entry["skipped"] += 1
                continue
            record["brand"] = brand_name
            record["channel"] = channel
            record["collected_at"] = now
            record["search_term"] = term
            fetch_content = _CONTENT_FETCHERS.get(channel)
            if fetch_content is not None:
                try:
                    record["content"] = fetch_content(record)
                except Exception:
                    record["content"] = ""
                time.sleep(_CONTENT_FETCH_DELAY_SECONDS)
            if db.insert_mention(record):
                entry["inserted"] += 1
            else:
                entry["skipped"] += 1

    if ok_terms == 0:
        entry["ok"] = 0
    entry["message"] = "; ".join(term_errors)

    db.insert_run_log(entry)
    return entry
