import gc
import sqlite3
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


def test_get_mentions_since_default_limit_does_not_silently_truncate_recent_history():
    """LIMIT 5000이 기본값이면 최근 이력이 그보다 많을 때(예: "최근 30일" 집계) 조용히
    잘려서 graph_queries.py의 카테고리 집계가 실제로는 최근 7일치만 반영하는 사고가
    있었다(2026-08-28). 기본 limit을 충분히 크게 유지해야 한다."""
    import inspect

    default_limit = inspect.signature(db.get_mentions_since).parameters["limit"].default

    assert default_limit >= 50000


def test_get_policy_events_since_excludes_older_than_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_policy_event({**_policy_event(url="https://p/1"), "collected_at": recent})
    db.insert_policy_event({**_policy_event(url="https://p/2"), "collected_at": old})

    results = db.get_policy_events_since(days=30)

    assert [r["url"] for r in results] == ["https://p/1"]


def test_get_policy_events_since_default_limit_does_not_silently_truncate_recent_history():
    import inspect

    default_limit = inspect.signature(db.get_policy_events_since).parameters["limit"].default

    assert default_limit >= 50000


def test_count_mentions_between_selects_correct_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    this_week = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    last_week = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": this_week})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": last_week})

    assert db.count_mentions_between(7, 0) == 1
    assert db.count_mentions_between(14, 7) == 1
    assert db.count_mentions_between(14, 0) == 2


def test_get_mentions_between_selects_correct_window_and_does_not_depend_on_recency(tmp_path, monkeypatch):
    """get_mentions_since는 '최신순 LIMIT'이라 최근 데이터가 많으면 그보다 오래된 요청
    구간이 통째로 잘릴 수 있다. get_mentions_between은 명시적 날짜 구간을 WHERE로 걸기
    때문에, 아주 최근 행(very_recent)이 있어도 구간 안의 더 오래된 행(older_in_window)이
    "최신 N건"에서 밀려나 사라지지 않고 둘 다 반환되어야 한다."""
    _isolate(tmp_path, monkeypatch)
    very_recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    older_in_window = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    too_old = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_mention({**_mention(url="https://x/1"), "title": "최근", "collected_at": very_recent})
    db.insert_mention({**_mention(url="https://x/2"), "title": "구간내오래된것", "collected_at": older_in_window})
    db.insert_mention({**_mention(url="https://x/3"), "title": "구간밖", "collected_at": too_old})

    results = db.get_mentions_between(14, 0)

    assert {r["title"] for r in results} == {"최근", "구간내오래된것"}


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


def test_update_mention_summary_persists_content_hash(tmp_path, monkeypatch):
    """content_hash를 같이 저장해둬야 summarizer가 나중에 content 변경을 감지해 요약을
    재생성할 수 있다(2026-08-28)."""
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]

    db.update_mention_summary(mention_id, "AI가 생성한 요약", content_hash="abc123")

    assert db.get_mentions()[0]["content_hash"] == "abc123"


def test_mentions_default_content_hash_to_empty_string(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    assert db.get_mentions()[0]["content_hash"] == ""


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


def test_get_run_batches_survives_non_numeric_fetched(tmp_path, monkeypatch):
    """.recover 복구 등으로 fetched가 숫자로 변환 불가능한 문자열로 들어간 경우
    sum()이 TypeError로 죽지 않고 그 행을 0으로 취급해야 한다."""
    _isolate(tmp_path, monkeypatch)
    db.insert_run_log(_run_log_entry(run_id="batch1"))
    with db._connect() as con:
        con.execute("UPDATE run_logs SET fetched = '깨짐' WHERE run_id = 'batch1'")

    batches = db.get_run_batches()

    assert batches[0]["fetched"] == 0


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


def test_mentions_with_blank_title_and_content_are_excluded_from_pending(tmp_path, monkeypatch):
    """title/content/snippet이 전부 빈 mention은 embed_text()가 즉시 None을 반환해 영원히
    임베딩에 실패한다 — vectorizer가 이런 건을 매 배치마다 "대기 중"으로 다시 집어 조용히
    반복 재시도하던 문제(2026-08-28)를 막는다. count와 목록 둘 다 이 건을 빼야 한다."""
    _isolate(tmp_path, monkeypatch)
    db.insert_mention({**_mention(url="https://x/1"), "title": "", "content": "", "snippet": ""})
    db.insert_mention(_mention(url="https://x/2"))

    assert db.count_mentions_without_embedding() == 1
    pending = db.get_mentions_without_embedding()
    assert len(pending) == 1
    assert pending[0]["snippet"] == "스니펫"


def test_update_mention_embedding_removes_it_from_pending(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]

    db.update_mention_embedding(mention_id, "[0.1, 0.2]")

    assert db.count_mentions_without_embedding() == 0
    assert db.get_mentions()[0]["embedding"] == "[0.1, 0.2]"


def test_clear_mention_embeddings_resets_to_pending(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    mention_id = db.get_mentions()[0]["id"]
    db.update_mention_embedding(mention_id, "깨진 텍스트")

    db.clear_mention_embeddings([mention_id])

    assert db.get_mentions()[0]["embedding"] == ""
    assert db.count_mentions_without_embedding() == 1


def test_policy_events_default_to_empty_embedding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })

    assert db.count_policy_events_without_embedding() == 1
    assert db.get_policy_events_without_embedding()[0]["title"] == "제목"


def test_clear_policy_event_embeddings_resets_to_pending(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({
        "source": "국토부", "title": "제목", "url": "https://p/1", "department": "",
        "announced_at": "2026-08-01", "view_count": 0, "collected_at": "2026-08-01 09:00:00",
    })
    event_id = db.get_policy_events()[0]["id"]
    db.update_policy_event_embedding(event_id, "깨진 텍스트")

    db.clear_policy_event_embeddings([event_id])

    assert db.get_policy_events()[0]["embedding"] == ""
    assert db.count_policy_events_without_embedding() == 1


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


def test_insert_webhook_send_log_and_get_webhook_send_logs_orders_most_recent_first(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_webhook_send_log({
        "ran_at": "2026-08-27 09:00:00", "trigger": "자동", "targets": 2, "sent": 2,
        "ok": 1, "message": "2/2개 웹훅 발송 성공 · 기사 10건",
    })
    db.insert_webhook_send_log({
        "ran_at": "2026-08-27 18:00:00", "trigger": "수동", "targets": 2, "sent": 1,
        "ok": 0, "message": "1/2개 웹훅 발송 성공 · 기사 12건",
    })

    logs = db.get_webhook_send_logs()

    assert [l["trigger"] for l in logs] == ["수동", "자동"]
    assert logs[0]["sent"] == 1
    assert logs[0]["ok"] == 0


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


def test_coerce_ints_normalizes_string_none_and_garbage_values():
    rows = [
        {"view_count": "700"},
        {"view_count": None},
        {"view_count": "완전히-깨진값"},
        {"view_count": 42},
    ]

    result = db._coerce_ints(rows, "view_count")

    assert [r["view_count"] for r in result] == [700, None, 0, 42]


def test_get_policy_events_survives_non_numeric_view_count(tmp_path, monkeypatch):
    """.recover 복구 등으로 INTEGER 컬럼에 숫자로 변환 불가능한 문자열이 들어간 경우를
    재현한다 — 화면에서 f"{view_count:,}" 포맷이나 >= 비교를 할 때 TypeError로 죽지 않고
    0으로 정규화되어야 한다."""
    _isolate(tmp_path, monkeypatch)
    db.insert_policy_event({**_policy_event(url="https://x/1"), "view_count": 50})
    event_id = db.get_policy_events()[0]["id"]
    with db._connect() as con:
        con.execute("UPDATE policy_events SET view_count = '깨짐' WHERE id = ?", [event_id])

    events = db.get_policy_events()

    assert events[0]["view_count"] == 0


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


def test_get_distinct_mention_dates_drops_unparseable_collected_at(tmp_path, monkeypatch):
    """.recover 복구 등으로 collected_at이 NULL이거나 날짜로 해석 불가능한 값이 되면
    SQL date()가 NULL을 반환하는데, 그 NULL이 다른 날짜 문자열과 섞여 브리핑 화면에서
    정렬될 때 TypeError('<' not supported between NoneType and str)로 죽었었다."""
    _isolate(tmp_path, monkeypatch)
    db.insert_mention({**_mention(url="https://x/1"), "collected_at": "2026-08-05 09:00:00"})
    db.insert_mention({**_mention(url="https://x/2"), "collected_at": "완전히 깨진 값"})
    db.insert_mention({**_mention(url="https://x/3"), "collected_at": "2026-08-06 09:00:00"})

    dates = db.get_distinct_mention_dates()

    assert dates == {"2026-08-05", "2026-08-06"}
    assert None not in dates


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


def test_backup_database_creates_restorable_snapshot(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    backup_path = db.backup_database()

    assert backup_path.exists()
    con = sqlite3.connect(backup_path)
    assert con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0] == 1
    con.close()


def test_backup_database_keeps_only_recent_n_backups(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(db, "_BACKUP_KEEP", 2)
    db.insert_mention(_mention(url="https://x/1"))

    paths = [db.backup_database() for _ in range(4)]

    remaining = list((tmp_path / "db_backups").glob("news_*.db"))
    assert len(remaining) == 2
    # 가장 최근 2개는 남아있어야 한다
    for p in paths[-2:]:
        assert p.exists()


def test_is_healthy_true_for_normal_database(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    assert db.is_healthy() is True


def _truncate_in_half(path):
    """페이지 상당수를 통째로 잘라내 sqlite3가 확실히 손상으로 인식하게 만든다 —
    헤더 근처 바이트 몇 개만 건드리는 건 SQLite가 의외로 잘 버텨서 재현이 안 된다.
    Windows에서는 db.py의 커넥션이 명시적으로 close()되지 않고 GC에 의존하는데,
    바로 직전까지 많은 insert가 있었으면 아직 안 닫힌 핸들 때문에 rename/truncate가
    막힐 수 있어 gc.collect()로 정리한다(Linux 프로덕션에서는 발생하지 않는, 테스트
    환경 한정 이슈)."""
    gc.collect()
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.truncate(size // 2)


def test_is_healthy_false_for_corrupted_file(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for i in range(200):
        db.insert_mention(_mention(url=f"https://x/{i}"))
    _truncate_in_half(db.DB_PATH)

    assert db.is_healthy() is False


def test_restore_latest_backup_returns_none_when_no_backups_exist(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert db.restore_latest_backup() is None


def test_restore_latest_backup_replaces_corrupted_db_and_preserves_it(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.backup_database()
    for i in range(2, 52):
        db.insert_mention(_mention(url=f"https://x/{i}"))  # 백업 이후 추가된 건 - 복구하면 사라짐

    _truncate_in_half(db.DB_PATH)
    assert db.is_healthy() is False

    gc.collect()
    restored_from = db.restore_latest_backup()

    assert restored_from is not None
    assert db.is_healthy() is True
    assert db.count_mentions() == 1
    failed_copies = list(tmp_path.glob("news.db.autofailed-*"))
    assert len(failed_copies) == 1


def test_init_db_self_heals_when_db_already_corrupted_at_startup(tmp_path, monkeypatch):
    """app.py는 스크립트 재실행마다 맨 앞에서 init_db()를 부르고, 그게 실패하면 스케줄러
    (10분 주기 자동 복구)가 아예 시작되지 못한다 — 즉 init_db() 자신이 스케줄러를 기다리지
    않고 부팅 시점에 바로 복구해야 한다(2026-08-20 사고: 배포 재시작 후 손상된 채로 몇
    분이 지나도 scheduler.log에 기록이 전혀 없었음 — start_scheduler_thread()가 그 앞
    줄에서 매번 죽어서 호출조차 안 됐던 것)."""
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))
    db.backup_database()
    db.insert_mention(_mention(url="https://x/2"))  # 백업 이후 추가 - 복구하면 사라짐

    gc.collect()
    _truncate_in_half(db.DB_PATH)

    db.init_db()  # 예외 없이 통과해야 한다 - 내부에서 자가복구 후 진행

    assert db.is_healthy() is True
    assert db.count_mentions() == 1


def test_init_db_does_not_touch_healthy_db(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_mention(_mention(url="https://x/1"))

    db.init_db()

    assert db.count_mentions() == 1


def test_get_agent_chat_sessions_is_empty_for_unknown_ip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    assert db.get_agent_chat_sessions("192.168.1.1") == []


def test_append_agent_chat_message_then_get_returns_one_session_with_message(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    message_id = db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "안녕")

    assert db.get_agent_chat_sessions("192.168.1.1") == [
        {"started_at": "2026-08-20 10:00", "messages": [
            {"id": message_id, "role": "user", "content": "안녕",
             "insufficient": False, "web_search_done": False},
        ]},
    ]


def test_append_agent_chat_message_returns_the_new_row_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    first_id = db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "하나")
    second_id = db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "둘")

    assert second_id != first_id
    assert isinstance(first_id, int)


def test_mark_agent_chat_message_web_search_done_updates_only_that_message(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target_id = db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "assistant", "답변1")
    other_id = db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "assistant", "답변2")

    db.mark_agent_chat_message_web_search_done(target_id)

    messages = {m["id"]: m for m in db.get_agent_chat_sessions("192.168.1.1")[0]["messages"]}
    assert messages[target_id]["web_search_done"] is True
    assert messages[other_id]["web_search_done"] is False


def test_append_agent_chat_message_preserves_order_within_a_session(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "질문1")
    db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "assistant", "답변1")
    db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "질문2")

    sessions = db.get_agent_chat_sessions("192.168.1.1")

    assert len(sessions) == 1
    contents = [m["content"] for m in sessions[0]["messages"]]
    assert contents == ["질문1", "답변1", "질문2"]


def test_append_agent_chat_message_groups_into_separate_sessions_by_started_at(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    db.append_agent_chat_message("192.168.1.1", "2026-08-20 09:00", "user", "지난 대화")
    db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "새 대화")

    sessions = db.get_agent_chat_sessions("192.168.1.1")

    assert [s["started_at"] for s in sessions] == ["2026-08-20 09:00", "2026-08-20 10:00"]
    assert sessions[0]["messages"][0]["content"] == "지난 대화"
    assert sessions[1]["messages"][0]["content"] == "새 대화"


def test_get_agent_chat_sessions_only_returns_messages_for_that_ip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    db.append_agent_chat_message("192.168.1.1", "2026-08-20 10:00", "user", "IP1 대화")
    db.append_agent_chat_message("192.168.1.2", "2026-08-20 10:00", "user", "IP2 대화")

    assert db.get_agent_chat_sessions("192.168.1.1")[0]["messages"][0]["content"] == "IP1 대화"
    assert db.get_agent_chat_sessions("192.168.1.2")[0]["messages"][0]["content"] == "IP2 대화"


def test_append_agent_chat_message_stores_insufficient_and_web_search_done_flags(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    db.append_agent_chat_message(
        "192.168.1.1", "2026-08-20 10:00", "assistant", "답변", insufficient=True,
    )
    db.append_agent_chat_message(
        "192.168.1.1", "2026-08-20 10:00", "assistant", "웹검색 답변", web_search_done=True,
    )

    messages = db.get_agent_chat_sessions("192.168.1.1")[0]["messages"]
    assert messages[0]["insufficient"] is True
    assert messages[0]["web_search_done"] is False
    assert messages[1]["insufficient"] is False
    assert messages[1]["web_search_done"] is True


def test_migrate_agent_chat_history_json_imports_existing_file_once(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    history_file = tmp_path / "agent_chat_history.json"
    history_file.write_text(
        '{"192.168.1.1": [{"started_at": "2026-08-19 09:00", "messages": '
        '[{"role": "user", "content": "예전 질문"}, '
        '{"role": "assistant", "content": "예전 답변", "insufficient": true}]}]}',
        encoding="utf-8",
    )

    db.migrate_agent_chat_history_json(history_file)

    sessions = db.get_agent_chat_sessions("192.168.1.1")
    messages = sessions[0]["messages"]
    assert [{k: v for k, v in m.items() if k != "id"} for m in messages] == [
        {"role": "user", "content": "예전 질문", "insufficient": False, "web_search_done": False},
        {"role": "assistant", "content": "예전 답변", "insufficient": True, "web_search_done": False},
    ]
    assert not history_file.exists()
    assert history_file.with_suffix(".json.migrated").exists()


def test_migrate_agent_chat_history_json_is_a_noop_when_file_missing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    db.migrate_agent_chat_history_json(tmp_path / "does_not_exist.json")

    assert db.get_agent_chat_sessions("192.168.1.1") == []


def test_migrate_agent_chat_history_json_does_not_duplicate_on_second_call(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    history_file = tmp_path / "agent_chat_history.json"
    history_file.write_text(
        '{"192.168.1.1": [{"started_at": "2026-08-19 09:00", "messages": '
        '[{"role": "user", "content": "예전 질문"}]}]}',
        encoding="utf-8",
    )

    db.migrate_agent_chat_history_json(history_file)
    db.migrate_agent_chat_history_json(history_file)  # 이미 옮겨진 뒤(파일 없음) 재호출

    sessions = db.get_agent_chat_sessions("192.168.1.1")
    assert len(sessions[0]["messages"]) == 1
    assert not list(tmp_path.glob("news.db.autofailed-*"))
