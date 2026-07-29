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


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(_MENTIONS_SQL)
        con.execute(_RUN_LOGS_SQL)
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
