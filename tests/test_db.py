from datetime import datetime, timedelta

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


def test_count_mentions_by_brand_counts_only_that_brand(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1", brand="직방"))
    db.insert_mention(_mention(url="https://x/2", brand="직방"))
    db.insert_mention(_mention(url="https://x/3", brand="다방"))

    assert db.count_mentions_by_brand("직방") == 2
    assert db.count_mentions_by_brand("다방") == 1
    assert db.count_mentions_by_brand("없는브랜드") == 0


def test_count_mentions_by_brand_since_excludes_older_than_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1", brand="직방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/2", brand="직방"), "collected_at": old})
    db.insert_mention({**_mention(url="https://x/3", brand="다방"), "collected_at": recent})

    assert db.count_mentions_by_brand_since("직방", days=30) == 1
    assert db.count_mentions_by_brand_since("다방", days=30) == 1
    assert db.count_mentions_by_brand_since("직방", days=60) == 2


def test_get_top_mentioned_brands_returns_descending_by_count(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1", brand="직방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/2", brand="직방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/3", brand="직방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/4", brand="다방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/5", brand="다방"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/6", brand="부동산114"), "collected_at": recent})

    top = db.get_top_mentioned_brands(days=30, limit=2)

    assert top == [{"brand": "직방", "count": 3}, {"brand": "다방", "count": 2}]


def test_get_mentions_since_excludes_older_than_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": recent})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": old})

    results = db.get_mentions_since(days=30)

    assert [r["url"] for r in results] == ["https://x/1"]


def test_get_policy_events_since_excludes_older_than_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_policy_event({**_policy_event(url="https://p/1"), "collected_at": recent})
    db.insert_policy_event({**_policy_event(url="https://p/2"), "collected_at": old})

    results = db.get_policy_events_since(days=30)

    assert [r["url"] for r in results] == ["https://p/1"]


def test_count_mentions_between_selects_correct_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    this_week = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    last_week = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": this_week})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": last_week})

    assert db.count_mentions_between(7, 0) == 1
    assert db.count_mentions_between(14, 7) == 1
    assert db.count_mentions_between(14, 0) == 2


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


def test_get_policy_source_counts_groups_by_source(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({**_policy_event(url="https://x/1"), "source": "국토부"})
    db.insert_policy_event({**_policy_event(url="https://x/2"), "source": "국토부"})
    db.insert_policy_event({**_policy_event(url="https://x/3"), "source": "LH"})

    assert db.get_policy_source_counts() == {"국토부": 2, "LH": 1}


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


def test_mentions_default_to_empty_embedding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    assert db.count_mentions_without_embedding() == 1
    assert db.get_mentions_without_embedding()[0]["title"] == "제목"


def test_update_mention_embedding_removes_it_from_pending(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]

    db.update_mention_embedding(mention_id, "[0.1, 0.2]")

    assert db.count_mentions_without_embedding() == 0
    assert db.get_mentions()[0]["embedding"] == "[0.1, 0.2]"


def test_policy_events_default_to_empty_embedding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })

    assert db.count_policy_events_without_embedding() == 1
    assert db.get_policy_events_without_embedding()[0]["title"] == "제목"


def test_update_policy_event_embedding_removes_it_from_pending(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })
    event_id = db.get_policy_events()[0]["id"]

    db.update_policy_event_embedding(event_id, "[0.3, 0.4]")

    assert db.count_policy_events_without_embedding() == 0
    assert db.get_policy_events()[0]["embedding"] == "[0.3, 0.4]"


def test_get_mention_embeddings_for_backup_skips_rows_without_embedding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.insert_mention(_mention(url="https://x/2"))
    with_embedding = next(m for m in db.get_mentions() if m["url"] == "https://x/1")
    db.update_mention_embedding(with_embedding["id"], "[0.1, 0.2]")

    backup = db.get_mention_embeddings_for_backup()

    assert backup == [{"url": "https://x/1", "embedding": "[0.1, 0.2]"}]


def test_restore_mention_embeddings_by_url_categorizes_restored_present_and_missing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.insert_mention(_mention(url="https://x/2"))
    already = next(m for m in db.get_mentions() if m["url"] == "https://x/2")
    db.update_mention_embedding(already["id"], "[9.0]")

    result = db.restore_mention_embeddings_by_url([
        {"url": "https://x/1", "embedding": "[1.0, 2.0]"},
        {"url": "https://x/2", "embedding": "[8.0]"},
        {"url": "https://x/does-not-exist", "embedding": "[1.0]"},
    ])

    assert result == {"restored": 1, "already_present": 1, "not_found": 1}
    by_url = {m["url"]: m["embedding"] for m in db.get_mentions()}
    assert by_url["https://x/1"] == "[1.0, 2.0]"
    assert by_url["https://x/2"] == "[9.0]"  # 덮어쓰지 않음


def test_restore_policy_event_embeddings_by_url_categorizes_restored_present_and_missing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })

    result = db.restore_policy_event_embeddings_by_url([
        {"url": "https://p/1", "embedding": "[1.0, 2.0]"},
        {"url": "https://p/does-not-exist", "embedding": "[1.0]"},
    ])

    assert result == {"restored": 1, "already_present": 0, "not_found": 1}
    assert db.get_policy_events()[0]["embedding"] == "[1.0, 2.0]"


def test_insert_vector_run_log_and_get_vector_run_logs_orders_most_recent_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_vector_run_log({
        "ran_at": "2026-08-06 09:00:00", "trigger": "수동", "source": "mentions",
        "fetched": 5, "inserted": 5, "skipped": 0, "ok": 1, "message": "", "run_id": "r1",
    })
    db.insert_vector_run_log({
        "ran_at": "2026-08-06 10:00:00", "trigger": "수동", "source": "policy_events",
        "fetched": 3, "inserted": 3, "skipped": 0, "ok": 1, "message": "", "run_id": "r1",
    })

    logs = db.get_vector_run_logs()

    assert [l["source"] for l in logs] == ["policy_events", "mentions"]


def test_log_activity_and_get_activity_log_orders_most_recent_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.log_activity("1.1.1.1", "오늘의 뉴스", "페이지 방문")
    db.log_activity("2.2.2.2", "뉴스 검색", "검색", "직방")

    logs = db.get_activity_log()

    assert [l["ip"] for l in logs] == ["2.2.2.2", "1.1.1.1"]
    assert logs[0]["detail"] == "직방"


def test_get_activity_log_filters_by_ip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.log_activity("1.1.1.1", "오늘의 뉴스", "페이지 방문")
    db.log_activity("2.2.2.2", "뉴스 검색", "검색", "직방")

    logs = db.get_activity_log(ip="1.1.1.1")

    assert len(logs) == 1
    assert logs[0]["ip"] == "1.1.1.1"


def test_count_activity_log_counts_all_ips(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.log_activity("1.1.1.1", "오늘의 뉴스", "페이지 방문")
    db.log_activity("2.2.2.2", "뉴스 검색", "검색", "직방")

    assert db.count_activity_log() == 2


def test_distinct_activity_ips_returns_sorted_unique_ips(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.log_activity("2.2.2.2", "뉴스 검색", "검색", "직방")
    db.log_activity("1.1.1.1", "오늘의 뉴스", "페이지 방문")
    db.log_activity("1.1.1.1", "브리핑", "페이지 방문")

    assert db.distinct_activity_ips() == ["1.1.1.1", "2.2.2.2"]


def test_count_activity_log_by_action_filters_action_and_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.log_activity("1.1.1.1", "PDF 보고서", "PDF 생성")
    db.log_activity("1.1.1.1", "PDF 보고서", "PDF 생성")
    db.log_activity("2.2.2.2", "오늘의 뉴스", "페이지 방문")
    old_ts = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    with db._connect() as con:
        con.execute(
            "UPDATE activity_log SET ts = ? WHERE action = 'PDF 생성' AND ip = '1.1.1.1' "
            "AND id = (SELECT MIN(id) FROM activity_log WHERE action = 'PDF 생성')",
            [old_ts],
        )

    assert db.count_activity_log_by_action("PDF 생성", days=30) == 1
    assert db.count_activity_log_by_action("PDF 생성", days=60) == 2
    assert db.count_activity_log_by_action("페이지 방문", days=30) == 1


def test_get_top_viewed_policy_events_orders_by_view_count_desc(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({**_policy_event(url="https://x/1"), "view_count": 50})
    db.insert_policy_event({**_policy_event(url="https://x/2"), "view_count": 300})
    db.insert_policy_event({**_policy_event(url="https://x/3"), "view_count": 120})

    top = db.get_top_viewed_policy_events(limit=2)

    assert [t["view_count"] for t in top] == [300, 120]


def _isolate_small_vectors(tmp_path, monkeypatch):
    """vec0 가상 테이블은 컬럼 차원이 고정이라, 실제 3072차원 대신 테스트용 4차원
    벡터를 쓰도록 VECTOR_DIM을 낮춘다 — DB 파일도 매번 새로 만들어지므로 테스트 간
    차원 충돌은 없다."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(db, "VECTOR_DIM", 4)


def test_upsert_and_search_mention_vectors_orders_by_distance(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.insert_mention(_mention(url="https://x/2"))
    ids = [r["id"] for r in db.get_mentions()]

    db.upsert_mention_vector(ids[0], [1.0, 0.0, 0.0, 0.0])
    db.upsert_mention_vector(ids[1], [0.0, 1.0, 0.0, 0.0])

    results = db.search_mention_vectors([0.9, 0.1, 0.0, 0.0], top_k=2)

    assert [r["id"] for r in results] == [ids[0], ids[1]]
    assert results[0]["distance"] < results[1]["distance"]
    assert results[0]["title"] == "제목"


def test_upsert_mention_vector_replaces_existing_vector_for_same_id(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]

    db.upsert_mention_vector(mention_id, [1.0, 0.0, 0.0, 0.0])
    db.upsert_mention_vector(mention_id, [0.0, 0.0, 1.0, 0.0])

    assert db.count_mention_vector_index() == 1
    results = db.search_mention_vectors([0.0, 0.0, 1.0, 0.0], top_k=1)
    assert results[0]["id"] == mention_id


def test_upsert_and_search_policy_vectors_orders_by_distance(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목1", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })
    db.insert_policy_event({
        "source": "국토부", "title": "제목2", "url": "https://p/2", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })
    ids = [r["id"] for r in db.get_policy_events()]

    db.upsert_policy_vector(ids[0], [1.0, 0.0, 0.0, 0.0])
    db.upsert_policy_vector(ids[1], [0.0, 1.0, 0.0, 0.0])

    results = db.search_policy_vectors([0.9, 0.1, 0.0, 0.0], top_k=2)

    assert [r["id"] for r in results] == [ids[0], ids[1]]


def test_get_mentions_missing_vector_index_excludes_already_indexed(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.insert_mention(_mention(url="https://x/2"))
    ids = [r["id"] for r in db.get_mentions()]
    db.update_mention_embedding(ids[0], "[1.0, 0.0, 0.0, 0.0]")
    db.update_mention_embedding(ids[1], "[0.0, 1.0, 0.0, 0.0]")
    db.upsert_mention_vector(ids[0], [1.0, 0.0, 0.0, 0.0])

    missing = db.get_mentions_missing_vector_index()

    assert [r["id"] for r in missing] == [ids[1]]


def test_get_policy_events_missing_vector_index_excludes_already_indexed(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })
    event_id = db.get_policy_events()[0]["id"]
    db.update_policy_event_embedding(event_id, "[1.0, 0.0, 0.0, 0.0]")

    missing = db.get_policy_events_missing_vector_index()

    assert [r["id"] for r in missing] == [event_id]


def test_count_mention_vector_index_and_policy_vector_index_start_at_zero(tmp_path, monkeypatch):
    _isolate_small_vectors(tmp_path, monkeypatch)

    assert db.count_mention_vector_index() == 0
    assert db.count_policy_vector_index() == 0


def _briefing_archive_record(date="2026-08-10"):
    return {
        "date": date,
        "channel_counts": {"네이버": 3, "매경API": 2},
        "channel_top_news": {
            "네이버": [{
                "title": "제목1", "url": "https://x/1", "brand": "직방",
                "channel": "네이버", "posted_at": "2026.08.10", "signal": "🏢 매물",
                "desc": "요약1",
            }],
        },
        "own_brand_news": [{
            "title": "프롭티어 소식", "url": "https://x/2", "brand": "프롭티어",
            "channel": "구글", "posted_at": "2026.08.10", "signal": "📰 일반", "desc": "요약2",
        }],
        "competitor_news": [],
        "market_news": [],
        "total_count": 5,
        "archived_at": "2026-08-11 00:05:00",
    }


def test_insert_briefing_archive_then_get_roundtrips_json_fields(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    inserted = db.insert_briefing_archive(_briefing_archive_record())

    assert inserted is True
    result = db.get_briefing_archive("2026-08-10")
    assert result["channel_counts"] == {"네이버": 3, "매경API": 2}
    assert result["own_brand_news"][0]["title"] == "프롭티어 소식"
    assert result["total_count"] == 5


def test_insert_briefing_archive_ignores_duplicate_date(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_briefing_archive(_briefing_archive_record())

    second = db.insert_briefing_archive(_briefing_archive_record())

    assert second is False


def test_get_briefing_archive_returns_none_when_not_archived(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert db.get_briefing_archive("2026-01-01") is None


def test_get_archived_briefing_dates_returns_set_of_dates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_briefing_archive(_briefing_archive_record(date="2026-08-10"))
    db.insert_briefing_archive(_briefing_archive_record(date="2026-08-11"))

    assert db.get_archived_briefing_dates() == {"2026-08-10", "2026-08-11"}


def test_get_earliest_mention_date_returns_min_date(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": "2026-08-05 10:00:00"})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": "2026-08-03 09:00:00"})

    assert db.get_earliest_mention_date() == "2026-08-03"


def test_get_earliest_mention_date_returns_none_when_no_mentions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert db.get_earliest_mention_date() is None


def test_get_mentions_by_collected_date_filters_to_exact_day_regardless_of_channel(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention({**_mention(url="https://x/1", channel="네이버"), "collected_at": "2026-08-05 09:00:00"})
    db.insert_mention({**_mention(url="https://x/2", channel="매경API"), "collected_at": "2026-08-05 23:00:00"})
    db.insert_mention({**_mention(url="https://x/3", channel="네이버"), "collected_at": "2026-08-06 09:00:00"})

    results = db.get_mentions_by_collected_date("2026-08-05")

    assert {r["url"] for r in results} == {"https://x/1", "https://x/2"}


def test_get_distinct_mention_dates_returns_unique_dates_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": "2026-08-05 09:00:00"})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": "2026-08-05 23:00:00"})
    db.insert_mention({**_mention(url="https://x/3"), "collected_at": "2026-08-06 09:00:00"})
    db.insert_mention({**_mention(url="https://x/4"), "collected_at": "2026-08-07 09:00:00"})

    assert db.get_distinct_mention_dates() == {"2026-08-05", "2026-08-06", "2026-08-07"}


def test_insert_api_usage_then_get_summary_aggregates_by_feature(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_api_usage(
        "summarizer", "gemini-2.5-flash", ok=True,
        prompt_tokens=10, output_tokens=5, thoughts_tokens=20, total_tokens=35,
    )
    db.insert_api_usage(
        "summarizer", "gemini-2.5-flash", ok=True,
        prompt_tokens=8, output_tokens=2, thoughts_tokens=5, total_tokens=15,
    )
    db.insert_api_usage("agent_chat", "gemini-2.5-flash", ok=False)

    summary = db.get_api_usage_summary(days=30)

    assert summary["summarizer"] == {
        "calls": 2, "prompt_tokens": 18, "output_tokens": 32, "tokens": 50, "failed": 0,
    }
    assert summary["agent_chat"] == {
        "calls": 1, "prompt_tokens": 0, "output_tokens": 0, "tokens": 0, "failed": 1,
    }


def test_get_api_usage_summary_excludes_entries_older_than_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_api_usage("summarizer", "gemini-2.5-flash", total_tokens=10)
    old_ts = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    with db._connect() as con:
        con.execute("UPDATE api_usage_log SET ts = ? WHERE feature = 'summarizer'", [old_ts])

    assert db.get_api_usage_summary(days=30) == {}


def test_get_api_usage_daily_groups_by_date(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_api_usage("summarizer", "gemini-2.5-flash", total_tokens=10)
    db.insert_api_usage("summarizer", "gemini-2.5-flash", total_tokens=20)

    daily = db.get_api_usage_daily(days=30)

    assert len(daily) == 1
    assert daily[0]["calls"] == 2
    assert daily[0]["tokens"] == 30
