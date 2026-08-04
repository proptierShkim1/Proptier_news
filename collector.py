"""
hana_p — 키워드 x 채널별 크롤러 실행, 저장, 실행이력 기록 조율.
"""

import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta

import db
from crawlers import daum as daum_crawler
from crawlers import dcinside as dcinside_crawler
from crawlers import google as google_crawler
from crawlers import hf as hf_crawler
from crawlers import hug as hug_crawler
from crawlers import lh as lh_crawler
from crawlers import molit as molit_crawler
from crawlers import naver as naver_crawler
from crawlers import naver_news_api as naver_news_api_crawler
from crawlers import reb as reb_crawler
from crawlers import seoul_opengov as seoul_opengov_crawler
from crawlers import sh as sh_crawler
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

_policy_state_lock = threading.Lock()
_active_policy_run_id: str | None = None
_policy_progress: dict[str, list[dict]] = {}

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


_NAVER_NEWS_CHANNEL = "네이버뉴스"

_naver_news_state_lock = threading.Lock()
_active_naver_news_run_id: str | None = None


def active_naver_news_run_id() -> str | None:
    """신규 게시물(active_run_id)·정책(active_policy_run_id)과 독립된 네이버뉴스 API
    수집 실행 상태를 추적한다."""
    with _naver_news_state_lock:
        return _active_naver_news_run_id


def start_background_naver_news_collection(trigger: str = "수동") -> str | None:
    """이미 진행 중인 네이버뉴스 API 수집이 없으면 데몬 스레드로 시작하고 run_id를
    반환한다. 신규 게시물/정책 수집과는 독립된 락이므로 서로 동시에 실행될 수 있다."""
    global _active_naver_news_run_id
    with _naver_news_state_lock:
        if _active_naver_news_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_naver_news_run_id = run_id

    def _worker():
        global _active_naver_news_run_id
        try:
            run_naver_news_collection(trigger=trigger, run_id=run_id)
        finally:
            with _naver_news_state_lock:
                _active_naver_news_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id


def run_naver_news_collection(
    trigger: str = "수동", on_progress=None, run_id: str | None = None
) -> list[dict]:
    """등록된 모든 브랜드 키워드로 네이버뉴스 API를 수집한다. 신규 게시물(4채널)과
    독립된 run_id/이력을 갖되, 노이즈/문맥/제외 필터링과 저장 스키마(_collect_one,
    mentions/run_logs)는 그대로 재사용한다."""
    cfg = load_keywords()
    context_words = cfg.get("context") or []
    exclude_terms = cfg.get("exclude") or []
    run_id = run_id or str(uuid.uuid4())[:8]
    brands = cfg["brands"]
    log_entries = []
    for i, brand_entry in enumerate(brands):
        entry = _collect_one(
            brand_entry, _NAVER_NEWS_CHANNEL, naver_news_api_crawler.search,
            trigger, run_id, context_words, exclude_terms,
        )
        log_entries.append(entry)
        if on_progress is not None:
            on_progress(entry)
        if i < len(brands) - 1:
            time.sleep(_REQUEST_DELAY_SECONDS)
    return log_entries


def _collect_press_releases(
    fetch_press_releases, source: str, days: int, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """모든 정책 소스 수집 함수가 공유하는 fetch→source 태깅→저장→이력 기록 로직.
    소스별 fetch_press_releases 자체가 실패 시 빈 리스트를 반환하는 것이 기본
    기대치이지만, 이 함수도 fetch_press_releases(start, today) 호출을 자체
    try/except로 감싸 그 호출 자체가 예외를 던지더라도 전파하지 않는다. run_id를
    주지 않으면(단일 소스 수동 실행 등) 새로 생성해 그 자체로 1건짜리 배치가 된다."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        records = fetch_press_releases(start, today)
        ok, message = 1, ""
    except Exception as e:
        records, ok, message = [], 0, str(e)

    inserted = 0
    skipped = 0
    for record in records:
        record["source"] = source
        record["collected_at"] = now
        if db.insert_policy_event(record):
            inserted += 1
        else:
            skipped += 1

    result = {"fetched": len(records), "inserted": inserted, "skipped": skipped}
    db.insert_policy_run_log({
        "ran_at": now, "trigger": trigger, "source": source, "run_id": run_id or str(uuid.uuid4())[:8],
        "ok": ok, "message": message, **result,
    })
    return result


def collect_molit_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """국토교통부 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(molit_crawler.fetch_press_releases, "국토부", days, trigger, run_id)


def collect_reb_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """한국부동산원 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(
        reb_crawler.fetch_press_releases, "한국부동산원", days, trigger, run_id
    )


def collect_lh_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """LH 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(lh_crawler.fetch_press_releases, "LH", days, trigger, run_id)


def collect_seoul_opengov_press_releases(
    days: int = 30, trigger: str = "수동", run_id: str | None = None
) -> dict:
    """서울시 정보소통광장 보도자료(주택/도시계획 관련만) 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(
        seoul_opengov_crawler.fetch_press_releases, "서울시", days, trigger, run_id
    )


def collect_hf_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """한국주택금융공사(HF) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(hf_crawler.fetch_press_releases, "HF", days, trigger, run_id)


def collect_hug_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """주택도시보증공사(HUG) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(hug_crawler.fetch_press_releases, "HUG", days, trigger, run_id)


def collect_sh_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """SH(서울주택도시공사) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(sh_crawler.fetch_press_releases, "SH", days, trigger, run_id)


def collect_all_policy_events(
    days: int = 30, on_progress=None, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """국토부/한국부동산원/LH/서울시/HF/HUG/SH 정책 데이터를 순서대로 모두 수집한다.
    소스별 함수가 각자 실패에 안전하므로(예외 대신 빈 리스트/스킵 처리) 한 소스의
    문제가 다른 소스 수집을 막지 않는다. 이에 더해 이 함수는 각 소스의
    collect_fn 호출 전체(fetch뿐 아니라 DB 저장까지)를 개별 try/except로 감싸,
    fetch 계층에서 걸러지지 않은 예기치 못한 예외(예: DB 쓰기 실패)가 나더라도
    해당 소스만 {"fetched": 0, "inserted": 0, "skipped": 0}으로 처리하고 나머지
    소스 수집은 계속 진행되도록 하는 바깥쪽 안전망 역할을 한다. 이 경우에도
    policy_run_logs에 ok=0, message=str(e)인 행을 남겨(내부 _collect_press_releases의
    실패 기록과 동일한 형태) get_policy_run_batches()가 이 배치를 정상(ok=1)으로
    잘못 집계하지 않도록 한다. 스케줄러가 자동 실행할 때도 사용한다. on_progress가
    주어지면 소스 하나가 끝날 때마다 (source, result)로 호출된다. 7개 소스 모두
    같은 run_id로 이력에 기록되어 "수집 이력"에서 1세트로 묶인다."""
    run_id = run_id or str(uuid.uuid4())[:8]
    sources = [
        ("국토부", collect_molit_press_releases),
        ("한국부동산원", collect_reb_press_releases),
        ("LH", collect_lh_press_releases),
        ("서울시", collect_seoul_opengov_press_releases),
        ("HF", collect_hf_press_releases),
        ("HUG", collect_hug_press_releases),
        ("SH", collect_sh_press_releases),
    ]
    results = {}
    for source, collect_fn in sources:
        try:
            result = collect_fn(days=days, trigger=trigger, run_id=run_id)
        except Exception as e:
            result = {"fetched": 0, "inserted": 0, "skipped": 0}
            db.insert_policy_run_log({
                "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "trigger": trigger, "source": source, "run_id": run_id,
                "ok": 0, "message": str(e), **result,
            })
        results[source] = result
        if on_progress is not None:
            on_progress(source, result)
    return results


def active_policy_run_id() -> str | None:
    """start_background_policy_collection()으로 시작된 정책 수집이 아직 진행 중이면
    그 run_id, 아니면 None. 브랜드 수집(active_run_id)과는 독립적으로 추적된다."""
    with _policy_state_lock:
        return _active_policy_run_id


def get_policy_progress(run_id: str) -> list[dict]:
    """start_background_policy_collection()이 진행되며 소스별로 쌓아온 결과 목록을 반환한다."""
    with _policy_state_lock:
        return list(_policy_progress.get(run_id, []))


def start_background_policy_collection(days: int = 30, trigger: str = "수동") -> str | None:
    """이미 진행 중인 백그라운드 정책 수집이 없으면 데몬 스레드로 시작하고 run_id를
    반환한다. 이미 진행 중이면 아무 것도 하지 않고 None을 반환한다(중복 실행 방지).
    이 run_id는 실시간 진행 조회(get_policy_progress)와 "수집 이력"(db.get_policy_run_batches)에
    동일하게 쓰인다."""
    global _active_policy_run_id
    with _policy_state_lock:
        if _active_policy_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_policy_run_id = run_id
        _policy_progress[run_id] = []

    def _on_progress(source, result):
        with _policy_state_lock:
            _policy_progress[run_id].append({"source": source, **result})

    def _worker():
        global _active_policy_run_id
        try:
            collect_all_policy_events(days=days, on_progress=_on_progress, trigger=trigger, run_id=run_id)
        finally:
            with _policy_state_lock:
                _active_policy_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id
