from datetime import datetime

import scheduler


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
    monkeypatch.setattr(scheduler, "_last_fired", "")
    monkeypatch.setattr(scheduler, "_last_fired_policy", "")
    monkeypatch.setattr(scheduler, "_last_fired_naver_news", "")


def test_tick_new_posts_and_policy_fire_on_their_own_independent_schedules(monkeypatch):
    """신규 게시물과 정부 정책은 각자 등록된 시각에만, 서로 무관하게 실행된다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    brand_calls = []
    policy_calls = []
    monkeypatch.setattr(scheduler.collector, "run_collection", lambda trigger: brand_calls.append(trigger))
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events",
        lambda days, trigger: policy_calls.append((days, trigger)) or {},
    )

    scheduler._tick()

    assert brand_calls == []  # 신규 게시물 스케줄에는 09:00이 없으므로 실행되지 않음
    assert policy_calls == [(scheduler._POLICY_COLLECTION_DAYS, "자동")]
    assert scheduler._last_fired == ""
    assert scheduler._last_fired_policy == "2026-07-16 09:00"


def test_tick_policy_does_not_fire_twice_for_same_minute(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events", lambda days, trigger: calls.append(days) or {}
    )

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_policy_collection(monkeypatch, caplog):
    """collect_all_policy_events()이 예외를 던져도 _tick()은 전파하지 않는다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})

    def boom(days, trigger):
        raise RuntimeError("policy collection failed")

    monkeypatch.setattr(scheduler.collector, "collect_all_policy_events", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_policy == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


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
    monkeypatch.setattr(scheduler.collector, "run_collection", lambda trigger: calls.append(("brand", trigger)))
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events",
        lambda days, trigger: calls.append(("policy", trigger)) or {},
    )
    monkeypatch.setattr(
        scheduler.collector, "start_background_naver_news_collection",
        lambda trigger: calls.append(("naver_news", trigger)),
    )

    scheduler._tick()

    assert calls == [("naver_news", "자동")]
    assert scheduler._last_fired_naver_news == "2026-07-16 09:00"


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

    assert scheduler._last_fired_naver_news == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)
