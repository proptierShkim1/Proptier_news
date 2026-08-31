import notifications


def _mention_batch(ran_at="2026-08-31 10:00:00", inserted=5, channels="네이버, 구글"):
    return {"ran_at": ran_at, "inserted": inserted, "channels": channels}


def _policy_batch(ran_at="2026-08-31 10:00:00", inserted=3, sources="국토부"):
    return {"ran_at": ran_at, "inserted": inserted, "sources": sources}


def test_build_notification_entries_includes_mention_and_policy_batches():
    entries = notifications.build_notification_entries(
        [_mention_batch(ran_at="2026-08-31 10:00:00", inserted=5)],
        [_policy_batch(ran_at="2026-08-31 09:00:00", inserted=3)],
    )

    assert len(entries) == 2
    assert "신규 게시물 5건" in entries[0]["text"]
    assert "정책 뉴스 3건" in entries[1]["text"]


def test_build_notification_entries_sorted_by_ran_at_descending():
    entries = notifications.build_notification_entries(
        [
            _mention_batch(ran_at="2026-08-31 09:00:00"),
            _mention_batch(ran_at="2026-08-31 11:00:00"),
        ],
        [_policy_batch(ran_at="2026-08-31 10:00:00")],
    )

    assert [e["ran_at"] for e in entries] == [
        "2026-08-31 11:00:00", "2026-08-31 10:00:00", "2026-08-31 09:00:00",
    ]


def test_build_notification_entries_skips_batches_with_nothing_inserted():
    """중복이라 전부 걸러진 배치(inserted=0)까지 "신규"라고 알리면 사용자가 헷갈린다."""
    entries = notifications.build_notification_entries(
        [_mention_batch(inserted=0)], [_policy_batch(inserted=0)],
    )

    assert entries == []


def test_count_unread_counts_entries_after_last_seen_at():
    entries = notifications.build_notification_entries(
        [
            _mention_batch(ran_at="2026-08-31 09:00:00"),
            _mention_batch(ran_at="2026-08-31 11:00:00"),
        ],
        [],
    )

    assert notifications.count_unread(entries, last_seen_at="2026-08-31 09:00:00") == 1
    assert notifications.count_unread(entries, last_seen_at="2026-08-31 08:00:00") == 2
    assert notifications.count_unread(entries, last_seen_at="2026-08-31 11:00:00") == 0


def test_count_unread_is_zero_when_last_seen_at_is_none():
    """세션 최초 진입 시(아직 last_seen_at을 정한 적 없음)엔 지난 이력을 전부 "안 읽음"으로
    띄우면 사용자가 방금 들어왔는데 배지가 잔뜩 떠서 오해하니, 0으로 시작한다."""
    entries = notifications.build_notification_entries([_mention_batch()], [])

    assert notifications.count_unread(entries, last_seen_at=None) == 0
