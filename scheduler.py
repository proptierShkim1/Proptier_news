"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import collector
from utils import load_collection_schedule

_POLL_SECONDS = 30
_last_fired = ""
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


def _tick() -> None:
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
        logger.exception("스케줄러 반복 실행 중 오류 발생")


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
