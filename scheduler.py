"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import collector
import summarizer
import vectorizer
from utils import (
    load_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
)

_POLL_SECONDS = 30
# 폴링 주기가 아니라 "혹시 한 번 놓쳐도 다음 실행에서 메꿔지도록" 여유를 둔 값 —
# 정책 게시판은 URL UNIQUE로 어차피 중복 저장되지 않으니 매번 겹치게 가져와도 안전하다.
_POLICY_COLLECTION_DAYS = 3
# PDF 상위 항목 AI 요약 미리 생성 주기 — 수집 스케줄과는 무관하게 별도로 돈다.
_PDF_PRESUMMARY_INTERVAL_MINUTES = 5
# 벡터화도 관리자가 "벡터화 진행"을 매번 누르지 않아도 되도록 별도 주기로 자동 실행한다.
_AUTO_VECTORIZE_INTERVAL_MINUTES = 10
_last_fired = ""
_last_fired_policy = ""
_last_fired_naver_news = ""
_last_pdf_presummary: datetime | None = None
_last_auto_vectorize: datetime | None = None
_lock = threading.Lock()
_started = False

_LOG_DIR = Path(__file__).resolve().parent / "data"
_LOG_FILE = _LOG_DIR / "scheduler.log"

logger = logging.getLogger("hana_p.scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)


def schedule_matches_now(times: list, now: datetime) -> bool:
    return now.strftime("%H:%M") in times


def _tick_new_posts() -> None:
    """신규 게시물(브랜드/시장 키워드) 자동 수집 체크. 예외를 상위로 전파하지 않는다."""
    global _last_fired
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired
        if not already_fired:
            schedules = load_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired = minute_key
                collector.run_collection(trigger="자동")
    except Exception:
        logger.exception("스케줄러(신규 게시물) 반복 실행 중 오류 발생")


def _tick_policy() -> None:
    """정부 정책 자동 수집 체크. 신규 게시물과 독립된 스케줄/예외 처리."""
    global _last_fired_policy
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_policy
        if not already_fired:
            schedules = load_policy_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_policy = minute_key
                result = collector.collect_all_policy_events(days=_POLICY_COLLECTION_DAYS, trigger="자동")
                logger.info("정책 데이터 자동 수집 결과: %s", result)
    except Exception:
        logger.exception("스케줄러(정부 정책) 반복 실행 중 오류 발생")


def _tick_naver_news() -> None:
    """네이버뉴스 API 자동 수집 체크. 신규 게시물/정부 정책과 독립된 스케줄/예외 처리."""
    global _last_fired_naver_news
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_naver_news
        if not already_fired:
            schedules = load_naver_news_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_naver_news = minute_key
                started_run_id = collector.start_background_naver_news_collection(trigger="자동")
                logger.info("네이버뉴스 API 자동 수집 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(네이버뉴스 API) 반복 실행 중 오류 발생")


def _tick_pdf_presummary() -> None:
    """PDF 보고서 상위 5개 항목의 AI 요약을 백그라운드에서 미리 만들어 DB에 저장한다.
    렌더링 시점(views/report.py)에 처음 요약을 만들면 Gemini 호출을 기다려야 해서 첫
    페이지 로딩이 느려지므로, 수집 스케줄과 별도로 일정 주기마다 미리 돌려 둔다. 앱
    시작 직후(첫 tick)에도 바로 한 번 실행된다."""
    global _last_pdf_presummary
    try:
        now = datetime.now()
        with _lock:
            due = _last_pdf_presummary is None or (
                now - _last_pdf_presummary >= timedelta(minutes=_PDF_PRESUMMARY_INTERVAL_MINUTES)
            )
        if due:
            with _lock:
                _last_pdf_presummary = now
            updated = summarizer.presummarize_top_pdf_items()
            if updated:
                logger.info("PDF 상위 항목 AI 요약 미리 생성: %d건", updated)
    except Exception:
        logger.exception("스케줄러(PDF 요약 미리 생성) 반복 실행 중 오류 발생")


def _tick_auto_vectorize() -> None:
    """새로 수집된 뉴스·정책을 관리자가 "벡터화 진행" 버튼을 매번 누르지 않아도 자동으로
    벡터화한다. start_background_vectorize()가 이미 진행 중인 벡터화는 알아서 건너뛰므로
    (모듈 레벨 lock+active_run_id), 이 tick은 그냥 일정 주기마다 "새로 돌 게 있는지"만
    확인해서 백그라운드 스레드를 새로 띄운다 — 벡터화 자체가 오래 걸려도 스케줄러의 다른
    tick을 막지 않는다."""
    global _last_auto_vectorize
    try:
        now = datetime.now()
        with _lock:
            due = _last_auto_vectorize is None or (
                now - _last_auto_vectorize >= timedelta(minutes=_AUTO_VECTORIZE_INTERVAL_MINUTES)
            )
        if due:
            with _lock:
                _last_auto_vectorize = now
            if vectorizer.has_api_keys():
                started_run_id = vectorizer.start_background_vectorize(trigger="자동")
                if started_run_id:
                    logger.info("자동 벡터화 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(자동 벡터화) 반복 실행 중 오류 발생")


def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API는 각자
    독립된 스케줄로 체크한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()
    _tick_pdf_presummary()
    _tick_auto_vectorize()


def _loop() -> None:
    while True:
        _tick()
        time.sleep(_POLL_SECONDS)


def start_scheduler_thread() -> None:
    """앱 프로세스당 1회만 스레드를 시작한다 (Streamlit 재실행에도 중복 방지)."""
    global _started
    if _started:
        return
    _started = True
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
