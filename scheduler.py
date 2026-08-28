"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import collector
import db
import news_feed
import notify
import summarizer
import vectorizer
from utils import (
    load_collection_schedule,
    load_mk_news_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    load_vector_collection_schedule,
    load_webhook_schedule,
)

_POLL_SECONDS = 30
# 폴링 주기가 아니라 "혹시 한 번 놓쳐도 다음 실행에서 메꿔지도록" 여유를 둔 값 —
# 정책 게시판은 URL UNIQUE로 어차피 중복 저장되지 않으니 매번 겹치게 가져와도 안전하다.
_POLICY_COLLECTION_DAYS = 3
# PDF 상위 항목 AI 요약 미리 생성 주기 — 수집 스케줄과는 무관하게 별도로 돈다.
_PDF_PRESUMMARY_INTERVAL_MINUTES = 5
# 2026-08-14~19에 원인이 제각각인 DB 손상이 반복됐다(pandas 세그폴트/OOM-kill/배포
# 재시작 타이밍/fsync 등) — 원인 하나하나를 막는 대신, 정기 백업 + 무결성 검사로
# "깨져도 사람 개입 없이 몇 분 안에 스스로 되돌아오는" 안전망을 둔다.
# 2026-08-26: news.db가 커지면서(mentions.embedding JSON) 백업 1건이 900MB에 달해,
# 20분마다 통째로 복사하면 그 순간 다른 요청들이 눈에 띄게 느려졌다 — 하루 1번(1440분)
# 으로 늘려 그 I/O 부담을 줄였다. 대신 복구 시 최대 손실 가능 데이터가 20분치에서
# 최대 24시간치로 늘어난다(db.py의 _BACKUP_KEEP=5와 합쳐 최근 5일 커버).
_DB_BACKUP_INTERVAL_MINUTES = 24 * 60
_DB_HEALTH_CHECK_INTERVAL_MINUTES = 10
_last_pdf_presummary: datetime | None = None
_last_db_backup: datetime | None = None
_last_db_health_check: datetime | None = None
_lock = threading.Lock()
_started = False

_LOG_DIR = Path(__file__).resolve().parent / "data"
_LOG_FILE = _LOG_DIR / "scheduler.log"
_LAST_FIRED_FILE = _LOG_DIR / "scheduler_last_fired.json"


def _load_last_fired_state() -> dict:
    """어느 스케줄이 어느 분(minute)에 마지막으로 실행됐는지를 파일로 들고 있는다 —
    이전에는 파이썬 전역 변수였는데, 그러면 서버를 재시작할 때마다 초기화돼서 "이번
    분에 이미 실행했는지"를 까먹는다. 배포 중 서버를 여러 번 재시작하는 동안 같은
    예정 시각(예: 18:00)에 벡터화/수집 배치가 몇 번씩 중복 실행되며 DB에 짧은 시간에
    과도한 쓰기가 몰려 손상으로 이어진 사고(2026-08-18)가 있어서, 프로세스 재시작에도
    살아남는 파일 기반 상태로 바꿨다."""
    try:
        return json.loads(_LAST_FIRED_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_last_fired_state(state: dict) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_FIRED_FILE.write_text(json.dumps(state), encoding="utf-8")


_last_fired_state = _load_last_fired_state()

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
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("new_posts")
        if not already_fired:
            schedules = load_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["new_posts"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                collector.start_background_collection(trigger="자동")
    except Exception:
        logger.exception("스케줄러(신규 게시물) 반복 실행 중 오류 발생")


def _tick_policy() -> None:
    """정부 정책 자동 수집 체크. 신규 게시물과 독립된 스케줄/예외 처리."""
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("policy")
        if not already_fired:
            schedules = load_policy_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["policy"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                started_run_id = collector.start_background_policy_collection(
                    days=_POLICY_COLLECTION_DAYS, trigger="자동"
                )
                logger.info("정책 데이터 자동 수집 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(정부 정책) 반복 실행 중 오류 발생")


def _tick_naver_news() -> None:
    """네이버뉴스 API 자동 수집 체크. 신규 게시물/정부 정책과 독립된 스케줄/예외 처리."""
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("naver_news")
        if not already_fired:
            schedules = load_naver_news_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["naver_news"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                started_run_id = collector.start_background_naver_news_collection(trigger="자동")
                logger.info("네이버뉴스 API 자동 수집 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(네이버뉴스 API) 반복 실행 중 오류 발생")


def _tick_mk_news() -> None:
    """매경 API 자동 수집 체크. 다른 채널과 독립된 스케줄/예외 처리."""
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("mk_news")
        if not already_fired:
            schedules = load_mk_news_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["mk_news"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                started_run_id = collector.start_background_mk_news_collection(trigger="자동")
                logger.info("매경 API 자동 수집 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(매경 API) 반복 실행 중 오류 발생")


def _tick_webhook_send() -> None:
    """웹훅 발송 자동 체크. 다른 채널과 독립된 스케줄/예외 처리."""
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("webhook_send")
        if not already_fired:
            schedules = load_webhook_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["webhook_send"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                result = notify.send_daily_report(trigger="자동")
                logger.info("웹훅 자동 발송 완료 (%s/%s)", result["sent"], result["targets"])
    except Exception:
        logger.exception("스케줄러(웹훅 발송) 반복 실행 중 오류 발생")


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
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_state.get("vectorize")
        if not already_fired:
            schedules = load_vector_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_state["vectorize"] = minute_key
                    _save_last_fired_state(_last_fired_state)
                if vectorizer.has_api_keys():
                    started_run_id = vectorizer.start_background_vectorize(trigger="자동")
                    logger.info("벡터화 자동 실행 시작 (run_id=%s)", started_run_id)
    except Exception:
        logger.exception("스케줄러(벡터화) 반복 실행 중 오류 발생")


def _tick_db_backup() -> None:
    """news.db 전체를 주기적으로 안전하게(SQLite 온라인 백업 API) 스냅샷 떠 둔다 —
    손상 시 사람이 sqlite3 .recover로 몇 시간씩 포렌식 복구하는 대신, 이 백업으로
    빠르게 되돌리기 위함."""
    global _last_db_backup
    try:
        now = datetime.now()
        with _lock:
            due = _last_db_backup is None or (
                now - _last_db_backup >= timedelta(minutes=_DB_BACKUP_INTERVAL_MINUTES)
            )
        if due:
            with _lock:
                _last_db_backup = now
            db.backup_database()
    except Exception:
        logger.exception("스케줄러(DB 백업) 반복 실행 중 오류 발생")


def _tick_db_health_check() -> None:
    """news.db 무결성을 주기적으로 확인하고, 손상이 감지되면 가장 최근 백업으로 즉시
    자동 복구한다. 이 앱은 매 요청마다 db._connect()로 새 커넥션을 열기 때문에,
    파일만 원상복구하면 스케줄러/웹 요청 모두 재시작 없이 바로 정상 파일을 쓰게 된다."""
    global _last_db_health_check
    try:
        now = datetime.now()
        with _lock:
            due = _last_db_health_check is None or (
                now - _last_db_health_check >= timedelta(minutes=_DB_HEALTH_CHECK_INTERVAL_MINUTES)
            )
        if not due:
            return
        with _lock:
            _last_db_health_check = now
        if db.is_healthy():
            return
        logger.error("news.db 무결성 검사 실패 — 최근 백업으로 자동 복구를 시도합니다")
        restored_from = db.restore_latest_backup()
        if restored_from:
            logger.error("news.db 자동 복구 완료 (백업: %s)", restored_from.name)
        else:
            logger.error("news.db 자동 복구 실패 — 사용 가능한 백업이 없습니다")
    except Exception:
        logger.exception("스케줄러(DB 무결성 검사) 반복 실행 중 오류 발생")


def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API/매경 API는
    각자 독립된 스케줄로 체크하고, 브리핑 아카이빙은 스케줄과 무관하게 매 tick 확인한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()
    _tick_mk_news()
    _tick_webhook_send()
    _tick_archive_briefings()
    _tick_pdf_presummary()
    _tick_auto_vectorize()
    _tick_db_health_check()
    _tick_db_backup()


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
