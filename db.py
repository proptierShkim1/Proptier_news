"""
hana_p — SQLite 저장소 (수집 데이터 + 실행 이력)
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "news.db"

_MENTIONS_SQL = """
CREATE TABLE IF NOT EXISTS mentions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    brand         TEXT NOT NULL,
    channel       TEXT NOT NULL,
    source_detail TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    snippet       TEXT DEFAULT '',
    posted_at     TEXT DEFAULT '',
    collected_at  TEXT NOT NULL,
    search_term   TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL DEFAULT ''
);
"""

_RUN_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS run_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at    TEXT NOT NULL,
    trigger   TEXT NOT NULL DEFAULT '수동',
    brand     TEXT NOT NULL,
    channel   TEXT NOT NULL,
    fetched   INTEGER DEFAULT 0,
    inserted  INTEGER DEFAULT 0,
    skipped   INTEGER DEFAULT 0,
    ok        INTEGER DEFAULT 1,
    message   TEXT DEFAULT '',
    run_id    TEXT NOT NULL DEFAULT ''
);
"""

_POLICY_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS policy_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    department   TEXT NOT NULL DEFAULT '',
    announced_at TEXT NOT NULL DEFAULT '',
    view_count   INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL
);
"""

_POLICY_RUN_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS policy_run_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at    TEXT NOT NULL,
    trigger   TEXT NOT NULL DEFAULT '수동',
    source    TEXT NOT NULL,
    fetched   INTEGER DEFAULT 0,
    inserted  INTEGER DEFAULT 0,
    skipped   INTEGER DEFAULT 0,
    ok        INTEGER DEFAULT 1,
    message   TEXT DEFAULT '',
    run_id    TEXT NOT NULL DEFAULT ''
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(_MENTIONS_SQL)
        con.execute(_RUN_LOGS_SQL)
        con.execute(_POLICY_EVENTS_SQL)
        con.execute(_POLICY_RUN_LOGS_SQL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mentions_collected_at ON mentions(collected_at)")


def insert_mention(record: dict) -> bool:
    """새 수집 데이터 1건 저장. url이 이미 있으면 False(중복 스킵), 새로 저장되면 True."""
    init_db()
    record = {
        **record,
        "search_term": record.get("search_term", ""),
        "content": record.get("content", ""),
    }
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO mentions "
            "(brand, channel, source_detail, title, url, snippet, posted_at, collected_at, "
            "search_term, content) "
            "VALUES (:brand, :channel, :source_detail, :title, :url, :snippet, :posted_at, "
            ":collected_at, :search_term, :content)",
            record,
        )
        return cur.rowcount > 0


def insert_run_log(entry: dict) -> None:
    init_db()
    entry = {**entry, "run_id": entry.get("run_id", "")}
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO run_logs "
            "(ran_at, trigger, brand, channel, fetched, inserted, skipped, ok, message, run_id) "
            "VALUES (:ran_at, :trigger, :brand, :channel, :fetched, :inserted, :skipped, :ok, :message, :run_id)",
            entry,
        )


def get_mentions(brand: str = "", channel: str = "", limit: int = 3000) -> list[dict]:
    init_db()
    query = "SELECT * FROM mentions WHERE 1=1"
    params = {"limit": limit}
    if brand:
        query += " AND brand = :brand"
        params["brand"] = brand
    if channel:
        query += " AND channel = :channel"
        params["channel"] = channel
    query += " ORDER BY collected_at DESC LIMIT :limit"
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_mentions(ids: list[int]) -> int:
    if not ids:
        return 0
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        placeholders = ",".join("?" * len(ids))
        cur = con.execute(f"DELETE FROM mentions WHERE id IN ({placeholders})", ids)
        return cur.rowcount


def delete_all_mentions() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM mentions")
        return cur.rowcount


def get_run_logs(limit: int = 50) -> list[dict]:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM run_logs ORDER BY ran_at DESC LIMIT :limit", {"limit": limit}
        ).fetchall()
        return [dict(r) for r in rows]


_LEGACY_BATCH_GAP_SECONDS = 300


def get_run_batches(limit: int = 50) -> list[dict]:
    """수집 실행을 건바이건이 아니라 run_id 기준 1세트로 묶어서 반환한다."""
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM run_logs ORDER BY ran_at ASC, id ASC LIMIT 2000"
        ).fetchall()]

    groups: dict[str, list[dict]] = {}
    legacy_key = None
    legacy_last_at = None
    for row in rows:
        if row["run_id"]:
            key = row["run_id"]
        else:
            at = datetime.strptime(row["ran_at"], "%Y-%m-%d %H:%M:%S")
            if (
                legacy_key is None
                or (at - legacy_last_at).total_seconds() > _LEGACY_BATCH_GAP_SECONDS
            ):
                legacy_key = f"legacy-{row['id']}"
            legacy_last_at = at
            key = legacy_key
        groups.setdefault(key, []).append(row)

    batches = []
    for rows_in_group in groups.values():
        brands = []
        for r in rows_in_group:
            if r["brand"] not in brands:
                brands.append(r["brand"])
        channels = []
        for r in rows_in_group:
            if r["channel"] not in channels:
                channels.append(r["channel"])
        messages = [r["message"] for r in rows_in_group if r["message"]]
        batches.append({
            "ran_at": min(r["ran_at"] for r in rows_in_group),
            "trigger": rows_in_group[0]["trigger"],
            "brands": ", ".join(brands),
            "channels": ", ".join(channels),
            "combinations": len(rows_in_group),
            "fetched": sum(r["fetched"] for r in rows_in_group),
            "inserted": sum(r["inserted"] for r in rows_in_group),
            "skipped": sum(r["skipped"] for r in rows_in_group),
            "ok": 1 if all(r["ok"] for r in rows_in_group) else 0,
            "message": "; ".join(messages),
        })

    batches.sort(key=lambda b: b["ran_at"], reverse=True)
    return batches[:limit]


def insert_policy_event(record: dict) -> bool:
    """새 정책 이벤트 1건 저장. url이 이미 있으면 False(중복 스킵), 새로 저장되면 True."""
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO policy_events "
            "(source, title, url, department, announced_at, view_count, collected_at) "
            "VALUES (:source, :title, :url, :department, :announced_at, :view_count, :collected_at)",
            record,
        )
        return cur.rowcount > 0


def get_policy_events(department: str = "", limit: int = 3000) -> list[dict]:
    init_db()
    query = "SELECT * FROM policy_events WHERE 1=1"
    params = {"limit": limit}
    if department:
        query += " AND department = :department"
        params["department"] = department
    query += " ORDER BY announced_at DESC LIMIT :limit"
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_policy_events(ids: list[int]) -> int:
    """주어진 id들의 정책 이벤트를 삭제. 삭제된 건수를 반환."""
    if not ids:
        return 0
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        placeholders = ",".join("?" * len(ids))
        cur = con.execute(f"DELETE FROM policy_events WHERE id IN ({placeholders})", ids)
        return cur.rowcount


def delete_all_policy_events() -> int:
    """policy_events 테이블의 모든 행을 삭제하고 삭제된 건수를 반환한다."""
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM policy_events")
        return cur.rowcount


def insert_policy_run_log(entry: dict) -> None:
    init_db()
    entry = {**entry, "run_id": entry.get("run_id", "")}
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO policy_run_logs "
            "(ran_at, trigger, source, fetched, inserted, skipped, ok, message, run_id) "
            "VALUES (:ran_at, :trigger, :source, :fetched, :inserted, :skipped, :ok, :message, :run_id)",
            entry,
        )


def get_policy_run_logs(limit: int = 50) -> list[dict]:
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM policy_run_logs ORDER BY ran_at DESC LIMIT :limit", {"limit": limit}
        ).fetchall()
        return [dict(r) for r in rows]


def get_policy_run_batches(limit: int = 50) -> list[dict]:
    """정책 수집 실행을 run_id 기준 1세트로 묶어서 반환한다. 이 테이블은 run_id 도입 이후
    신설된 것이라 run_logs/get_run_batches와 달리 레거시(run_id 없는) 행에 대한
    시간-간격 추정 묶음 로직이 필요 없다."""
    init_db()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM policy_run_logs ORDER BY ran_at ASC, id ASC LIMIT 2000"
        ).fetchall()]

    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = row["run_id"] or f"legacy-{row['id']}"
        groups.setdefault(key, []).append(row)

    batches = []
    for rows_in_group in groups.values():
        sources = []
        for r in rows_in_group:
            if r["source"] not in sources:
                sources.append(r["source"])
        messages = [r["message"] for r in rows_in_group if r["message"]]
        batches.append({
            "ran_at": min(r["ran_at"] for r in rows_in_group),
            "trigger": rows_in_group[0]["trigger"],
            "sources": ", ".join(sources),
            "fetched": sum(r["fetched"] for r in rows_in_group),
            "inserted": sum(r["inserted"] for r in rows_in_group),
            "skipped": sum(r["skipped"] for r in rows_in_group),
            "ok": 1 if all(r["ok"] for r in rows_in_group) else 0,
            "message": "; ".join(messages),
        })

    batches.sort(key=lambda b: b["ran_at"], reverse=True)
    return batches[:limit]
