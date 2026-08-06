import db


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")


def _mention(url="https://x/1", brand="직방", channel="네이버"):
    return {
        "brand": brand,
        "channel": channel,
        "source_detail": "블로그",
        "title": "제목",
        "url": url,
        "snippet": "스니펫",
        "posted_at": "",
        "collected_at": "2026-07-16 09:00:00",
    }


def test_get_mentions_channels_filter_matches_any_of_the_given_channels(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1", channel="네이버"))
    db.insert_mention(_mention(url="https://x/2", channel="구글"))
    db.insert_mention(_mention(url="https://x/3", channel="다음"))

    results = db.get_mentions(channels=["네이버", "구글"])

    assert {r["url"] for r in results} == {"https://x/1", "https://x/2"}


def test_get_mentions_channels_empty_list_returns_nothing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1", channel="네이버"))

    assert db.get_mentions(channels=[]) == []


def test_get_mentions_without_channels_falls_back_to_single_channel_filter(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1", channel="네이버"))
    db.insert_mention(_mention(url="https://x/2", channel="구글"))

    results = db.get_mentions(channel="네이버")

    assert [r["url"] for r in results] == ["https://x/1"]


def test_insert_mention_defaults_summary_to_empty_string(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    result = db.get_mentions()[0]

    assert result["summary"] == ""


def test_update_mention_summary_persists_summary_for_given_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]

    db.update_mention_summary(mention_id, "AI가 생성한 요약")

    assert db.get_mentions()[0]["summary"] == "AI가 생성한 요약"


def test_ensure_column_adds_missing_column_to_existing_table(tmp_path, monkeypatch):
    """summary 컬럼이 없는 기존 DB 파일도 init_db() 호출만으로 안전하게 마이그레이션되는지 확인."""
    import sqlite3

    _isolate(tmp_path, monkeypatch)
    with sqlite3.connect(db.DB_PATH) as con:
        con.execute("""
            CREATE TABLE mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL, channel TEXT NOT NULL,
                source_detail TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                snippet TEXT DEFAULT '', posted_at TEXT DEFAULT '', collected_at TEXT NOT NULL,
                search_term TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT ''
            )
        """)

    db.init_db()

    with sqlite3.connect(db.DB_PATH) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(mentions)")}
    assert "summary" in cols


def _policy_event(url="https://www.molit.go.kr/dtl.jsp?id=1", title="제목",
                   department="주택토지", announced_at="2026-07-20", view_count=100,
                   collected_at="2026-07-24 09:00:00"):
    return {
        "source": "국토부", "title": title, "url": url, "department": department,
        "announced_at": announced_at, "view_count": view_count, "collected_at": collected_at,
    }


def test_insert_policy_event_returns_true_for_new_url(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert db.insert_policy_event(_policy_event()) is True


def test_insert_policy_event_returns_false_for_duplicate_url(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event(_policy_event())

    assert db.insert_policy_event(_policy_event()) is False


def test_count_policy_events_returns_total_row_count(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event(_policy_event(url="https://x/1"))
    db.insert_policy_event(_policy_event(url="https://x/2"))

    assert db.count_policy_events() == 2


def test_get_policy_events_filters_by_department_and_orders_by_announced_at_desc(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event(_policy_event(
        url="https://x/1", department="주택토지", announced_at="2026-07-20",
    ))
    db.insert_policy_event(_policy_event(
        url="https://x/2", department="건설", announced_at="2026-07-22",
    ))

    all_events = db.get_policy_events()
    housing_only = db.get_policy_events(department="주택토지")

    assert len(all_events) == 2
    assert all_events[0]["url"] == "https://x/2"  # 최신 announced_at 먼저
    assert len(housing_only) == 1
    assert housing_only[0]["department"] == "주택토지"


def test_delete_policy_events_removes_given_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event(_policy_event(url="https://x/1"))
    db.insert_policy_event(_policy_event(url="https://x/2"))
    id_to_delete = next(e["id"] for e in db.get_policy_events() if e["url"] == "https://x/1")

    deleted = db.delete_policy_events([id_to_delete])

    assert deleted == 1
    remaining = db.get_policy_events()
    assert len(remaining) == 1
    assert remaining[0]["url"] == "https://x/2"


def test_delete_all_policy_events_removes_every_row_and_returns_count(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event(_policy_event(url="https://x/1"))
    db.insert_policy_event(_policy_event(url="https://x/2"))

    deleted = db.delete_all_policy_events()

    assert deleted == 2
    assert db.get_policy_events() == []


def test_delete_all_policy_events_never_touches_mentions_table(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention())
    db.insert_policy_event(_policy_event())

    db.delete_all_policy_events()

    assert len(db.get_mentions()) == 1  # mentions는 그대로 남아있어야 함


def _run_log_entry(brand="프롭티어", channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"):
    return {
        "ran_at": ran_at, "trigger": "수동", "brand": brand, "channel": channel,
        "fetched": 1, "inserted": 1, "skipped": 0, "ok": 1, "message": "", "run_id": run_id,
    }


def _policy_run_log_entry(source="국토부", ok=1, run_id="batch1"):
    return {
        "ran_at": "2026-07-28 09:00:00",
        "trigger": "수동",
        "source": source,
        "fetched": 1,
        "inserted": 1,
        "skipped": 0,
        "ok": ok,
        "message": "",
        "run_id": run_id,
    }


def test_insert_policy_run_log_and_get_policy_run_logs_orders_most_recent_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = _policy_run_log_entry(source="국토부")
    first["ran_at"] = "2026-07-28 09:00:00"
    second = _policy_run_log_entry(source="LH")
    second["ran_at"] = "2026-07-28 10:00:00"
    db.insert_policy_run_log(first)
    db.insert_policy_run_log(second)

    logs = db.get_policy_run_logs()

    assert len(logs) == 2
    assert logs[0]["source"] == "LH"  # 최신 ran_at 먼저


def test_get_policy_run_batches_groups_sources_sharing_a_run_id_into_one_row(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e1 = _policy_run_log_entry(source="국토부", run_id="batch1")
    e1["ran_at"] = "2026-07-28 09:00:00"
    e2 = _policy_run_log_entry(source="LH", run_id="batch1")
    e2["ran_at"] = "2026-07-28 09:00:02"
    db.insert_policy_run_log(e1)
    db.insert_policy_run_log(e2)

    batches = db.get_policy_run_batches()

    assert len(batches) == 1
    assert batches[0]["sources"] == "국토부, LH"
    assert batches[0]["fetched"] == 2


def test_get_policy_run_batches_orders_most_recent_batch_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    older = _policy_run_log_entry(source="국토부", run_id="batch1")
    older["ran_at"] = "2026-07-28 09:00:00"
    newer = _policy_run_log_entry(source="LH", run_id="batch2")
    newer["ran_at"] = "2026-07-28 10:00:00"
    db.insert_policy_run_log(older)
    db.insert_policy_run_log(newer)

    batches = db.get_policy_run_batches()

    assert [b["ran_at"] for b in batches] == ["2026-07-28 10:00:00", "2026-07-28 09:00:00"]


def test_get_policy_run_batches_marks_ok_false_when_any_source_failed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ok_entry = _policy_run_log_entry(source="국토부", ok=1, run_id="batch1")
    ok_entry["ran_at"] = "2026-07-28 09:00:00"
    fail_entry = _policy_run_log_entry(source="LH", ok=0, run_id="batch1")
    fail_entry["ran_at"] = "2026-07-28 09:00:02"
    fail_entry["message"] = "타임아웃"
    db.insert_policy_run_log(ok_entry)
    db.insert_policy_run_log(fail_entry)

    batches = db.get_policy_run_batches()

    assert batches[0]["ok"] == 0
    assert "타임아웃" in batches[0]["message"]


def test_get_run_batches_without_channels_filter_returns_everything(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_run_log(_run_log_entry(channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"))
    db.insert_run_log(_run_log_entry(channel="네이버뉴스API", run_id="batch2", ran_at="2026-08-04 10:00:00"))

    batches = db.get_run_batches()

    assert len(batches) == 2


def test_get_run_batches_channels_filter_only_includes_matching_channels(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_run_log(_run_log_entry(channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"))
    db.insert_run_log(_run_log_entry(channel="네이버뉴스API", run_id="batch2", ran_at="2026-08-04 10:00:00"))

    brand_batches = db.get_run_batches(channels=["네이버", "구글", "다음", "커뮤니티"])
    naver_news_batches = db.get_run_batches(channels=["네이버뉴스API"])

    assert len(brand_batches) == 1
    assert brand_batches[0]["channels"] == "네이버"
    assert len(naver_news_batches) == 1
    assert naver_news_batches[0]["channels"] == "네이버뉴스API"


def test_get_run_batches_channels_filter_splits_mixed_channel_batch(tmp_path, monkeypatch):
    """Test that channels filter correctly isolates rows from a single run_id with multiple channels."""
    _isolate(tmp_path, monkeypatch)
    # Insert two rows with the same run_id but different channels
    naver_entry = _run_log_entry(channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00")
    naver_entry["fetched"] = 5
    naver_entry["inserted"] = 4
    db.insert_run_log(naver_entry)

    naver_news_entry = _run_log_entry(channel="네이버뉴스API", run_id="batch1", ran_at="2026-08-04 09:00:02")
    naver_news_entry["fetched"] = 3
    naver_news_entry["inserted"] = 2
    db.insert_run_log(naver_news_entry)

    # Filter by 네이버 only
    naver_batches = db.get_run_batches(channels=["네이버"])
    # Filter by 네이버뉴스API only
    naver_news_batches = db.get_run_batches(channels=["네이버뉴스API"])

    # Each filter should return exactly one batch with only that channel's data
    assert len(naver_batches) == 1
    assert naver_batches[0]["channels"] == "네이버"
    assert naver_batches[0]["combinations"] == 1
    assert naver_batches[0]["fetched"] == 5
    assert naver_batches[0]["inserted"] == 4

    assert len(naver_news_batches) == 1
    assert naver_news_batches[0]["channels"] == "네이버뉴스API"
    assert naver_news_batches[0]["combinations"] == 1
    assert naver_news_batches[0]["fetched"] == 3
    assert naver_news_batches[0]["inserted"] == 2
