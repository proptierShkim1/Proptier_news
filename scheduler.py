"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import collector
import news_feed
import summarizer
import vectorizer
from utils import (
    load_collection_schedule,
    load_mk_news_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    load_vector_collection_schedule,
)

_POLL_SECONDS = 30
# 폴링 주기가 아니라 "혹시 한 번 놓쳐도 다음 실행에서 메꿔지도록" 여유를 둔 값 —
# 정책 게시판은 URL UNIQUE로 어차피 중복 저장되지 않으니 매번 겹치게 가져와도 안전하다.
_POLICY_COLLECTION_DAYS = 3
# PDF 상위 항목 AI 요약 미리 생성 주기 — 수집 스케줄과는 무관하게 별도로 돈다.
_PDF_PRESUMMARY_INTERVAL_MINUTES = 5
_last_fired = ""
_last_fired_policy = ""
_last_fired_naver_news = ""
_last_fired_mk_news = ""
_last_fired_vectorize = ""
_last_pdf_presummary: datetime | None = None
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
                collector.start_background_collection(trigger="자동")
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
                started_run_id = collector.start_background_policy_collection(
                    days=_POLICY_COLLECTION_DAYS, trigger="자동"
                )
                logger.info("정책 데이터 자동 수집 시작 (run_id=%s)", started_run_id)
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


def _tick_mk_news() -> None:
    """매경 API 자동 수집 체크. 다른 채널과 독립된 스케줄/예외 처리."""
    global _last_fired_mk_news
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_mk_news
        if not already_fired:
            schedules = load_mk_news_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_mk_news = minute_key
                started_run_id = collector.start_background_mk_news_collection(trigger="자동")
                logger.info("매경 API 자동 수집 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(매경 API) 반복 실행 중 오류 발생")


def _tick_archive_briefings() -> None:
    """일별 브리핑 확정(아카이빙). 정확한 시각 일치가 아니라 "아직 확정 안 된 과거
    날짜가 있으면 즉시 확정"하는 방식이라 tick을 놓쳐도 다음 tick에서 만회된다."""
    try:
        archived = news_feed.archive_pending_briefings()
        if archived:
            logger.info("브리핑 아카이빙 완료: %s", ", ".join(sorted(archived)))
    except Exception:
        logger.exception("스케줄러(브리핑 아카이빙) 반복 실행 중 오류 발생")


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
    """등록된 시각에 벡터화를 자동 실행한다 — 설정 → 벡터 데이터 탭에서 관리자가 직접
    등록/관리하는 스케줄을 따르며, 신규 게시물/정책/네이버뉴스 API와 완전히 독립된
    스케줄이다(다른 자동 수집이 하나도 등록 안 된 경우와 동일하게, 벡터화 시각도 등록
    안 하면 자동 실행되지 않고 수동 "벡터화 진행" 버튼만 동작한다)."""
    global _last_fired_vectorize
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_vectorize
        if not already_fired:
            schedules = load_vector_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_vectorize = minute_key
                if vectorizer.has_api_keys():
                    started_run_id = vectorizer.start_background_vectorize(trigger="자동")
                    logger.info("벡터화 자동 실행 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(벡터화) 반복 실행 중 오류 발생")


def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API/매경 API는
    각자 독립된 스케줄로 체크하고, 브리핑 아카이빙은 스케줄과 무관하게 매 tick 확인한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()
    _tick_mk_news()
    _tick_archive_briefings()
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
