from datetime import datetime, timedelta

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
    # 신규 게시물/정책/네이버뉴스 스케줄과 무관한 PDF 요약 미리 생성/자동 벡터화 tick은
    # 실제 Gemini/DB를 건드리므로, 이 tick들을 직접 테스트하는 케이스가 아니면 아무 일도
    # 하지 않게 한다.
    monkeypatch.setattr(scheduler, "_tick_pdf_presummary", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_auto_vectorize", lambda: None)


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

    assert scheduler._last_fired_policy == "2026-07-16 09:00"
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
    assert scheduler._last_fired == "2026-07-16 09:00"


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
    monkeypatch.setattr(scheduler, "_last_fired_vectorize", "")
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
    assert scheduler._last_fired_vectorize == "2026-07-16 09:00"


def test_tick_auto_vectorize_does_not_fire_when_time_not_in_schedule(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_fired_vectorize", "")
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
    monkeypatch.setattr(scheduler, "_last_fired_vectorize", "")
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
    monkeypatch.setattr(scheduler, "_last_fired_vectorize", "")
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
    assert scheduler._last_fired_vectorize == "2026-07-16 09:00"


def test_tick_auto_vectorize_swallows_exception(monkeypatch, caplog):
    monkeypatch.setattr(scheduler, "_last_fired_vectorize", "")
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_vector_collection_schedule", lambda: {"times": ["09:00"]})
    monkeypatch.setattr(scheduler.vectorizer, "has_api_keys", lambda: True)

    def boom(trigger):
        raise RuntimeError("vectorize boom")

    monkeypatch.setattr(scheduler.vectorizer, "start_background_vectorize", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_auto_vectorize()

    assert scheduler._last_fired_vectorize == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)
