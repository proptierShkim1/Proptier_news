import time

import collector
import db


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(collector, "_active_policy_run_id", None)
    monkeypatch.setattr(collector, "_policy_progress", {})
    monkeypatch.setattr(collector, "_active_naver_news_run_id", None)


def _fake_release(url, announced_at="2026-07-20"):
    return {
        "title": "제목", "url": url, "department": "주택토지",
        "announced_at": announced_at, "view_count": 10,
    }


def _wait_until(condition, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


def test_collect_molit_press_releases_saves_records_and_returns_summary(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.molit_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1"), _fake_release("https://x/2")],
    )

    result = collector.collect_molit_press_releases(days=30)

    assert result == {"fetched": 2, "inserted": 2, "skipped": 0}
    events = db.get_policy_events()
    assert len(events) == 2
    assert events[0]["source"] == "국토부"


def test_collect_molit_press_releases_skips_duplicate_urls(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.molit_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1"), _fake_release("https://x/1")],
    )

    result = collector.collect_molit_press_releases(days=30)

    assert result == {"fetched": 2, "inserted": 1, "skipped": 1}


def test_collect_molit_press_releases_records_a_policy_run_log(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.molit_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_molit_press_releases(days=30, trigger="수동")

    logs = db.get_policy_run_logs()
    assert len(logs) == 1
    assert logs[0]["source"] == "국토부"
    assert logs[0]["trigger"] == "수동"
    assert logs[0]["fetched"] == 1


def test_collect_reb_press_releases_tags_source_as_한국부동산원(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.reb_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_reb_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "한국부동산원"


def test_collect_lh_press_releases_tags_source_as_LH(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.lh_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_lh_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "LH"


def test_collect_seoul_opengov_press_releases_tags_source_as_서울시(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.seoul_opengov_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_seoul_opengov_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "서울시"


def test_collect_hf_press_releases_tags_source_as_HF(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.hf_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_hf_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "HF"


def test_collect_hug_press_releases_tags_source_as_HUG(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.hug_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_hug_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "HUG"


def test_collect_sh_press_releases_tags_source_as_SH(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        collector.sh_crawler, "fetch_press_releases",
        lambda start, end: [_fake_release("https://x/1")],
    )

    collector.collect_sh_press_releases(days=30)

    assert db.get_policy_events()[0]["source"] == "SH"


def test_collect_all_policy_events_collects_all_seven_sources(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for crawler_name, url_prefix in [
        ("molit_crawler", "molit"), ("reb_crawler", "reb"), ("lh_crawler", "lh"),
        ("seoul_opengov_crawler", "seoul"), ("hf_crawler", "hf"),
        ("hug_crawler", "hug"), ("sh_crawler", "sh"),
    ]:
        crawler = getattr(collector, crawler_name)
        monkeypatch.setattr(
            crawler, "fetch_press_releases",
            lambda start, end, p=url_prefix: [_fake_release(f"https://{p}/1")],
        )

    result = collector.collect_all_policy_events(days=30)

    assert len(result) == 7
    assert all(r["inserted"] == 1 for r in result.values())
    events = db.get_policy_events()
    assert len(events) == 7


def test_collect_all_policy_events_one_source_failing_does_not_block_others(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def boom(start, end):
        raise RuntimeError("network down")

    monkeypatch.setattr(collector.molit_crawler, "fetch_press_releases", boom)
    for crawler_name in [
        "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(
            getattr(collector, crawler_name), "fetch_press_releases",
            lambda start, end, c=crawler_name: [_fake_release(f"https://{c}/1")],
        )

    result = collector.collect_all_policy_events(days=30)

    assert result["국토부"] == {"fetched": 0, "inserted": 0, "skipped": 0}
    assert result["LH"]["inserted"] == 1


def test_collect_all_policy_events_one_collect_fn_raising_does_not_block_others(tmp_path, monkeypatch):
    """fetch 계층이 아니라 소스의 collect_fn 전체(예: DB 저장 단계)에서 예기치
    못한 예외가 나도 collect_all_policy_events는 전파하지 않고 해당 소스만
    0으로 처리한 채 나머지 6개 소스 수집을 계속 진행해야 한다."""
    _isolate(tmp_path, monkeypatch)

    def boom(days, trigger, run_id):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(collector, "collect_molit_press_releases", boom)
    for crawler_name in [
        "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(
            getattr(collector, crawler_name), "fetch_press_releases",
            lambda start, end, c=crawler_name: [_fake_release(f"https://{c}/1")],
        )

    result = collector.collect_all_policy_events(days=30)

    assert len(result) == 7
    assert result["국토부"] == {"fetched": 0, "inserted": 0, "skipped": 0}
    assert result["한국부동산원"]["inserted"] == 1
    assert result["LH"]["inserted"] == 1
    assert result["서울시"]["inserted"] == 1
    assert result["HF"]["inserted"] == 1
    assert result["HUG"]["inserted"] == 1
    assert result["SH"]["inserted"] == 1
    events = db.get_policy_events()
    assert len(events) == 6

    # 바깥쪽 안전망이 예외를 삼키고 마는 게 아니라, 내부 _collect_press_releases의
    # 실패 기록과 동일하게 policy_run_logs에 ok=0/message를 남겨야 한다. 그래야
    # get_policy_run_batches()가 이 배치를 정상(ok=1)으로 잘못 집계하지 않는다.
    logs = db.get_policy_run_logs(limit=50)
    molit_logs = [l for l in logs if l["source"] == "국토부"]
    assert len(molit_logs) == 1
    assert molit_logs[0]["ok"] == 0
    assert "db write failed" in molit_logs[0]["message"]

    batches = db.get_policy_run_batches()
    batch = next(b for b in batches if "국토부" in b["sources"])
    assert batch["ok"] == 0


def test_collect_all_policy_events_calls_on_progress_per_source(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for crawler_name in [
        "molit_crawler", "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(getattr(collector, crawler_name), "fetch_press_releases", lambda start, end: [])

    seen = []
    collector.collect_all_policy_events(days=30, on_progress=lambda source, result: seen.append((source, result)))

    assert len(seen) == 7


def test_collect_all_policy_events_logs_all_sources_under_one_shared_run_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for crawler_name in [
        "molit_crawler", "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(getattr(collector, crawler_name), "fetch_press_releases", lambda start, end: [])

    collector.collect_all_policy_events(days=30, trigger="자동")

    logs = db.get_policy_run_logs()
    assert len(logs) == 7
    run_ids = {log["run_id"] for log in logs}
    assert len(run_ids) == 1

    batches = db.get_policy_run_batches()
    assert len(batches) == 1
    assert batches[0]["sources"].count(",") == 6  # 7개 소스가 콤마 6개로 이어짐


def test_active_policy_run_id_is_none_when_nothing_running(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert collector.active_policy_run_id() is None


def test_start_background_policy_collection_runs_and_completes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for crawler_name in [
        "molit_crawler", "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(
            getattr(collector, crawler_name), "fetch_press_releases",
            lambda start, end, c=crawler_name: [_fake_release(f"https://{c}/1")],
        )

    run_id = collector.start_background_policy_collection(days=30)

    assert run_id is not None
    assert _wait_until(lambda: collector.active_policy_run_id() is None)
    progress = collector.get_policy_progress(run_id)
    assert len(progress) == 7
    events = db.get_policy_events()
    assert len(events) == 7
    batches = db.get_policy_run_batches()
    assert batches[0]["fetched"] == 7


def test_start_background_policy_collection_returns_none_when_already_running(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    started = []
    blocker = []

    def slow_fetch(start, end):
        started.append(1)
        while not blocker:
            time.sleep(0.01)
        return []

    monkeypatch.setattr(collector.molit_crawler, "fetch_press_releases", slow_fetch)
    for crawler_name in [
        "reb_crawler", "lh_crawler", "seoul_opengov_crawler",
        "hf_crawler", "hug_crawler", "sh_crawler",
    ]:
        monkeypatch.setattr(getattr(collector, crawler_name), "fetch_press_releases", lambda start, end: [])

    first_run_id = collector.start_background_policy_collection(days=30)
    assert _wait_until(lambda: len(started) == 1, timeout=1.0)
    assert _wait_until(lambda: collector.active_policy_run_id() == first_run_id, timeout=1.0)

    second_run_id = collector.start_background_policy_collection(days=30)

    assert second_run_id is None
    blocker.append(1)
    assert _wait_until(lambda: collector.active_policy_run_id() is None)


def _fake_naver_news_record(url, term="프롭티어"):
    return {
        "source_detail": "뉴스", "title": f"{term} 관련 뉴스", "url": url,
        "snippet": f"{term} 관련 요약", "posted_at": "2026.08.04",
    }


def _naver_news_keywords():
    return {"brands": [{"name": "프롭티어", "role": "own"}], "context": [], "exclude": []}


def test_run_naver_news_collection_saves_records_tagged_with_naver_news_channel(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(collector, "load_keywords", _naver_news_keywords)
    monkeypatch.setattr(
        collector.naver_news_api_crawler, "search",
        lambda term: [_fake_naver_news_record("https://x/1", term)],
    )

    entries = collector.run_naver_news_collection()

    assert len(entries) == 1
    assert entries[0]["channel"] == "네이버뉴스"
    mentions = db.get_mentions(channel="네이버뉴스")
    assert len(mentions) == 1
    assert mentions[0]["content"] == ""


def test_run_naver_news_collection_skips_duplicate_urls(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(collector, "load_keywords", _naver_news_keywords)
    monkeypatch.setattr(
        collector.naver_news_api_crawler, "search",
        lambda term: [_fake_naver_news_record("https://x/1", term), _fake_naver_news_record("https://x/1", term)],
    )

    entries = collector.run_naver_news_collection()

    assert entries[0]["fetched"] == 2
    assert entries[0]["inserted"] == 1
    assert entries[0]["skipped"] == 1


def test_run_naver_news_collection_is_independent_of_brand_and_policy_state(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(collector, "load_keywords", _naver_news_keywords)
    monkeypatch.setattr(collector.naver_news_api_crawler, "search", lambda term: [])

    collector.run_naver_news_collection()

    assert collector.active_run_id() is None
    assert collector.active_policy_run_id() is None


def test_active_naver_news_run_id_is_none_when_nothing_running(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert collector.active_naver_news_run_id() is None


def test_start_background_naver_news_collection_runs_and_completes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(collector, "load_keywords", _naver_news_keywords)
    monkeypatch.setattr(
        collector.naver_news_api_crawler, "search",
        lambda term: [_fake_naver_news_record("https://x/1", term)],
    )

    run_id = collector.start_background_naver_news_collection()

    assert run_id is not None
    assert _wait_until(lambda: collector.active_naver_news_run_id() is None)
    mentions = db.get_mentions(channel="네이버뉴스")
    assert len(mentions) == 1


def test_start_background_naver_news_collection_returns_none_when_already_running(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(collector, "load_keywords", _naver_news_keywords)
    started = []
    blocker = []

    def slow_search(term):
        started.append(1)
        while not blocker:
            time.sleep(0.01)
        return []

    monkeypatch.setattr(collector.naver_news_api_crawler, "search", slow_search)

    first_run_id = collector.start_background_naver_news_collection()
    assert _wait_until(lambda: len(started) == 1, timeout=1.0)
    assert _wait_until(lambda: collector.active_naver_news_run_id() == first_run_id, timeout=1.0)

    second_run_id = collector.start_background_naver_news_collection()

    assert second_run_id is None
    blocker.append(1)
    assert _wait_until(lambda: collector.active_naver_news_run_id() is None)
