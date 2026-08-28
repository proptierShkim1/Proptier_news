from datetime import datetime, timedelta

import pytest

import scheduler


@pytest.fixture(autouse=True)
def _isolate_last_fired_state(monkeypatch, tmp_path):
    """_last_fired_state는 서버 재시작에도 살아남도록 파일에 저장되는데, 테스트에서는
    실제 저장소 파일을 건드리면 안 되고 테스트 간에도 상태가 새지 않아야 한다 — 매
    테스트마다 격리된 임시 파일 경로를 쓰게 하면 실제 저장 함수를 그대로 써도 안전하다."""
    monkeypatch.setattr(scheduler, "_last_fired_state", {})
    monkeypatch.setattr(scheduler, "_LAST_FIRED_FILE", tmp_path / "scheduler_last_fired.json")


def test_last_fired_state_persists_across_process_restart():
    """2026-08-18 사고 재현: 예전엔 _last_fired_*가 파이썬 전역 변수라 서버를 재시작할
    때마다 초기화됐다 — 트러블슈팅 중 서버를 짧은 시간에 여러 번 재시작하면, 매번 새
    프로세스가 "이번 분엔 아직 안 돌렸다"고 착각해 같은 예정 시각(예: 18:00)에 벡터화
    배치가 몇 번씩 중복 실행되며 DB에 과도한 쓰기가 몰려 손상으로 이어졌다. 이제는
    파일에 저장되므로, 새 프로세스(=새로 읽은 상태)에서도 이미 발화한 분을 기억해야
    한다."""
    scheduler._save_last_fired_state({"vectorize": "2026-08-18 18:00"})

    reloaded = scheduler._load_last_fired_state()

    assert reloaded == {"vectorize": "2026-08-18 18:00"}


def test_schedule_matches_now_true_when_time_in_list():
    now = datetime(2026, 7, 16, 9, 0)
    assert scheduler.schedule_matches_now(["09:00", "13:00"], now) is True


def test_schedule_matches_now_false_when_time_not_in_list():
    now = datetime(2026, 7, 16, 9, 1)
    assert scheduler.schedule_matches_now(["09:00"], now) is False


def _fix_now(monkeypatch, fixed_now):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)


def _reset(monkeypatch):
    # 매경 API 스케줄은 이 스케줄을 직접 테스트하는 케이스가 아니면 빈 스케줄로
    # 고정해, 다른 tick 테스트가 실제 데이터 파일 유무에 좌우되지 않게 한다.
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": []})
    # 신규 게시물/정책/네이버뉴스 스케줄과 무관한 PDF 요약 미리 생성/자동 벡터화/브리핑
    # 아카이빙 tick은 실제 Gemini/DB를 건드리므로, 이 tick들을 직접 테스트하는 케이스가
    # 아니면 아무 일도 하지 않게 한다.
    monkeypatch.setattr(scheduler, "_tick_pdf_presummary", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_auto_vectorize", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_archive_briefings", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_db_backup", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_db_health_check", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_webhook_send", lambda: None)


def test_tick_new_posts_and_policy_fire_on_their_own_independent_schedules(monkeypatch):
    """신규 게시물과 정부 정책은 각자 등록된 시각에만, 서로 무관하게 실행된다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    brand_calls = []
    policy_calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_collection", lambda trigger: brand_calls.append(trigger)
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_policy_collection",
        lambda days, trigger: policy_calls.append((days, trigger)) or "run-1",
    )

    scheduler._tick()

    assert brand_calls == []  # 신규 게시물 스케줄에는 09:00이 없으므로 실행되지 않음
    assert policy_calls == [(scheduler._POLICY_COLLECTION_DAYS, "자동")]
    assert scheduler._last_fired_state.get("new_posts") is None
    assert scheduler._last_fired_state["policy"] == "2026-07-16 09:00"


def test_tick_policy_does_not_fire_twice_for_same_minute(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_policy_collection",
        lambda days, trigger: calls.append(days) or "run-1",
    )

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_policy_collection(monkeypatch, caplog):
    """start_background_policy_collection()이 예외를 던져도 _tick()은 전파하지 않는다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    def boom(days, trigger):
        raise RuntimeError("policy collection failed")

    monkeypatch.setattr(scheduler.collector, "start_background_policy_collection", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_state["policy"] == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_new_posts_fires_in_background_without_blocking(monkeypatch):
    """신규 게시물 자동 수집은 백그라운드 스레드로 시작되어야 한다 — 동기 호출이면
    이 tick이 오래 걸리는 동안 같은 스레드에서 순차 실행되는 정책/네이버뉴스/벡터화
    tick이 전부 지연되고, 그 사이 지나가버린 분(HH:MM)의 스케줄은 영영 스킵된다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_collection",
        lambda trigger: calls.append(trigger) or "run-1",
    )

    scheduler._tick()

    assert calls == ["자동"]
    assert scheduler._last_fired_state["new_posts"] == "2026-07-16 09:00"


def test_tick_swallows_exception_from_load_policy_collection_schedule(monkeypatch, caplog):
    """load_policy_collection_schedule()이 예외를 던져도 _tick()은 전파하지 않고 로깅한다.
    신규 게시물 체크는 이 예외와 무관하게 독립적으로 동작한다."""
    _reset(monkeypatch)
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})

    def boom():
        raise RuntimeError("policy schedule file corrupted")

    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", boom)
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_naver_news_fires_on_its_own_independent_schedule(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_collection", lambda trigger: calls.append(("brand", trigger))
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_policy_collection",
        lambda days, trigger: calls.append(("policy", trigger)) or "run-1",
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_naver_news_collection",
        lambda trigger: calls.append(("naver_news", trigger)),
    )

    scheduler._tick()

    assert calls == [("naver_news", "자동")]
    assert scheduler._last_fired_state["naver_news"] == "2026-07-16 09:00"


def test_tick_naver_news_does_not_fire_twice_for_same_minute(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_naver_news_collection",
        lambda trigger: calls.append(trigger),
    )

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_naver_news_collection(monkeypatch, caplog):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    def boom(trigger):
        raise RuntimeError("naver news collection failed")

    monkeypatch.setattr(scheduler.collector, "start_background_naver_news_collection", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_state["naver_news"] == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_mk_news_fires_on_its_own_independent_schedule(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_collection", lambda trigger: calls.append(("brand", trigger))
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_policy_collection",
        lambda days, trigger: calls.append(("policy", trigger)) or "run-1",
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_naver_news_collection",
        lambda trigger: calls.append(("naver_news", trigger)),
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_mk_news_collection",
        lambda trigger: calls.append(("mk_news", trigger)),
    )

    scheduler._tick()

    assert calls == [("mk_news", "자동")]
    assert scheduler._last_fired_state["mk_news"] == "2026-07-16 09:00"


def test_tick_mk_news_does_not_fire_twice_for_same_minute(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "start_background_mk_news_collection",
        lambda trigger: calls.append(trigger),
    )

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_mk_news_collection(monkeypatch, caplog):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": ["09:00"]})

    def boom(trigger):
        raise RuntimeError("mk news collection failed")

    monkeypatch.setattr(scheduler.collector, "start_background_mk_news_collection", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_state["mk_news"] == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_pdf_presummary_runs_immediately_on_first_call(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_pdf_presummary", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    calls = []
    monkeypatch.setattr(scheduler.summarizer, "presummarize_top_pdf_items", lambda: calls.append(1) or 0)

    scheduler._tick_pdf_presummary()

    assert calls == [1]
    assert scheduler._last_pdf_presummary == datetime(2026, 7, 16, 9, 0)


def test_tick_pdf_presummary_does_not_run_again_before_interval_elapses(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_pdf_presummary", datetime(2026, 7, 16, 9, 0))
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 2))
    calls = []
    monkeypatch.setattr(scheduler.summarizer, "presummarize_top_pdf_items", lambda: calls.append(1) or 0)

    scheduler._tick_pdf_presummary()

    assert calls == []


def test_tick_pdf_presummary_runs_again_after_interval_elapses(monkeypatch):
    monkeypatch.setattr(
        scheduler, "_last_pdf_presummary",
        datetime(2026, 7, 16, 9, 0) - timedelta(minutes=scheduler._PDF_PRESUMMARY_INTERVAL_MINUTES),
    )
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    calls = []
    monkeypatch.setattr(scheduler.summarizer, "presummarize_top_pdf_items", lambda: calls.append(1) or 0)

    scheduler._tick_pdf_presummary()

    assert calls == [1]


def test_tick_pdf_presummary_swallows_exception(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_pdf_presummary", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))

    def boom():
        raise RuntimeError("gemini boom")

    monkeypatch.setattr(scheduler.summarizer, "presummarize_top_pdf_items", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_pdf_presummary()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_auto_vectorize_fires_on_its_own_independent_schedule(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: True)
    calls = []
    monkeypatch.setattr(
        scheduler.vectorizer, "start_background_vectorize",
        lambda trigger: calls.append(trigger) or "run-1",
    )

    scheduler._tick_auto_vectorize()

    assert calls == ["자동"]
    assert scheduler._last_fired_state["vectorize"] == "2026-07-16 09:00"


def test_tick_auto_vectorize_does_not_fire_when_time_not_in_schedule(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 1))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: True)
    calls = []
    monkeypatch.setattr(
        scheduler.vectorizer, "start_background_vectorize", lambda trigger: calls.append(trigger),
    )

    scheduler._tick_auto_vectorize()

    assert calls == []


def test_tick_auto_vectorize_does_not_fire_twice_for_same_minute(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: True)
    calls = []
    monkeypatch.setattr(
        scheduler.vectorizer, "start_background_vectorize",
        lambda trigger: calls.append(trigger) or "run-1",
    )

    scheduler._tick_auto_vectorize()
    scheduler._tick_auto_vectorize()

    assert len(calls) == 1


def test_tick_auto_vectorize_skips_starting_a_run_when_no_api_keys(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: False)
    calls = []
    monkeypatch.setattr(
        scheduler.vectorizer, "start_background_vectorize", lambda trigger: calls.append(trigger),
    )

    scheduler._tick_auto_vectorize()

    assert calls == []
    # 스케줄 자체는 매칭되어 이번 분에 "발화"한 것으로 기록된다 — 다음 tick에서 다시
    # 시도하지 않지만, 다음 등록 시각에는 정상적으로 다시 시도한다.
    assert scheduler._last_fired_state["vectorize"] == "2026-07-16 09:00"


def test_tick_auto_vectorize_swallows_exception(monkeypatch, caplog):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: True)

    def boom(trigger):
        raise RuntimeError("vectorize boom")

    monkeypatch.setattr(scheduler.vectorizer, "start_background_vectorize", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_auto_vectorize()

    assert scheduler._last_fired_state["vectorize"] == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_db_backup_runs_immediately_on_first_call(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    calls = []
    monkeypatch.setattr(scheduler.db, "backup_database", lambda: calls.append(1))

    scheduler._tick_db_backup()

    assert calls == [1]
    assert scheduler._last_db_backup == datetime(2026, 7, 16, 9, 0)


def test_tick_db_backup_does_not_run_again_before_interval_elapses(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_db_backup", datetime(2026, 7, 16, 9, 0))
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 5))
    calls = []
    monkeypatch.setattr(scheduler.db, "backup_database", lambda: calls.append(1))

    scheduler._tick_db_backup()

    assert calls == []


def test_tick_db_backup_runs_again_after_interval_elapses(monkeypatch):
    monkeypatch.setattr(
        scheduler, "_last_db_backup",
        datetime(2026, 7, 16, 9, 0) - timedelta(minutes=scheduler._DB_BACKUP_INTERVAL_MINUTES),
    )
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    calls = []
    monkeypatch.setattr(scheduler.db, "backup_database", lambda: calls.append(1))

    scheduler._tick_db_backup()

    assert calls == [1]


def test_tick_db_backup_swallows_exception(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_db_backup", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))

    def boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(scheduler.db, "backup_database", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_db_backup()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_db_health_check_does_nothing_when_healthy(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_db_health_check", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler.db, "is_healthy", lambda: True)
    restore_calls = []
    monkeypatch.setattr(scheduler.db, "restore_latest_backup", lambda: restore_calls.append(1))

    scheduler._tick_db_health_check()

    assert restore_calls == []
    assert scheduler._last_db_health_check == datetime(2026, 7, 16, 9, 0)


def test_tick_db_health_check_does_not_run_again_before_interval_elapses(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_db_health_check", datetime(2026, 7, 16, 9, 0))
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 5))
    calls = []
    monkeypatch.setattr(scheduler.db, "is_healthy", lambda: calls.append(1) or True)

    scheduler._tick_db_health_check()

    assert calls == []


def test_tick_db_health_check_restores_latest_backup_when_unhealthy(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_db_health_check", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler.db, "is_healthy", lambda: False)
    restore_calls = []

    class FakePath:
        name = "news_20260716_0800.db"

    monkeypatch.setattr(scheduler.db, "restore_latest_backup", lambda: restore_calls.append(1) or FakePath())

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_db_health_check()

    assert restore_calls == [1]
    assert any("자동 복구 완료" in record.message for record in caplog.records)


def test_tick_db_health_check_logs_failure_when_no_backup_available(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_db_health_check", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler.db, "is_healthy", lambda: False)
    monkeypatch.setattr(scheduler.db, "restore_latest_backup", lambda: None)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_db_health_check()

    assert any("자동 복구 실패" in record.message for record in caplog.records)


def test_tick_db_health_check_swallows_exception(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_db_health_check", None)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler.db, "is_healthy", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_db_health_check()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_archive_briefings_calls_archive_pending_briefings(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler.news_feed, "archive_pending_briefings", lambda: calls.append(1) or ["2026-08-10"]
    )

    scheduler._tick_archive_briefings()

    assert calls == [1]


def test_tick_archive_briefings_swallows_exception(monkeypatch, caplog):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler.news_feed, "archive_pending_briefings", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_archive_briefings()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_webhook_send_fires_on_its_own_independent_schedule(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 18, 0))
    monkeypatch.setattr(scheduler, "load_webhook_schedule", lambda: {"times": ["18:00"]})
    calls = []
    monkeypatch.setattr(
        scheduler.notify, "send_daily_report",
        lambda trigger: calls.append(trigger) or {"targets": 1, "sent": 1},
    )

    scheduler._tick_webhook_send()

    assert calls == ["자동"]
    assert scheduler._last_fired_state["webhook_send"] == "2026-07-16 18:00"


def test_tick_webhook_send_does_not_fire_when_time_not_in_schedule(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 18, 1))
    monkeypatch.setattr(scheduler, "load_webhook_schedule", lambda: {"times": ["18:00"]})
    calls = []
    monkeypatch.setattr(scheduler.notify, "send_daily_report", lambda trigger: calls.append(trigger))

    scheduler._tick_webhook_send()

    assert calls == []


def test_tick_webhook_send_does_not_fire_twice_for_same_minute(monkeypatch):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 18, 0))
    monkeypatch.setattr(scheduler, "load_webhook_schedule", lambda: {"times": ["18:00"]})
    calls = []
    monkeypatch.setattr(
        scheduler.notify, "send_daily_report",
        lambda trigger: calls.append(trigger) or {"targets": 1, "sent": 1},
    )

    scheduler._tick_webhook_send()
    scheduler._tick_webhook_send()

    assert len(calls) == 1


def test_tick_webhook_send_swallows_exception(monkeypatch, caplog):
    _fix_now(monkeypatch, datetime(2026, 7, 16, 18, 0))
    monkeypatch.setattr(scheduler, "load_webhook_schedule", lambda: {"times": ["18:00"]})

    def boom(trigger):
        raise RuntimeError("teams down")

    monkeypatch.setattr(scheduler.notify, "send_daily_report", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_webhook_send()

    assert scheduler._last_fired_state["webhook_send"] == "2026-07-16 18:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_includes_archive_briefings_when_not_disabled(monkeypatch):
    """_reset()의 비활성화 없이 _tick()을 직접 호출하면 브리핑 아카이빙 tick도 함께 도는지
    확인 — _tick()에 실제로 연결됐는지 검증하는 목적."""
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "_tick_pdf_presummary", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_auto_vectorize", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_db_backup", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_db_health_check", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_webhook_send", lambda: None)
    calls = []
    monkeypatch.setattr(scheduler.news_feed, "archive_pending_briefings", lambda: calls.append(1) or [])

    scheduler._tick()

    assert calls == [1]
