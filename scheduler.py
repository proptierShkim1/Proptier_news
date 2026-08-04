"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import collector
from utils import (
    load_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
)

_POLL_SECONDS = 30
# 폴링 주기가 아니라 "혹시 한 번 놓쳐도 다음 실행에서 메꿔지도록" 여유를 둔 값 —
# 정책 게시판은 URL UNIQUE로 어차피 중복 저장되지 않으니 매번 겹치게 가져와도 안전하다.
_POLICY_COLLECTION_DAYS = 3
_last_fired = ""
_last_fired_policy = ""
_last_fired_naver_news = ""
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
                collector.run_naver_news_collection(trigger="자동")
    except Exception:
        logger.exception("스케줄러(네이버뉴스 API) 반복 실행 중 오류 발생")


def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API는 각자
    독립된 스케줄로 체크한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()


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
