"""
hana_p — SQLite 저장소 (수집 데이터 + 실행 이력)
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "news.db"


def _connect() -> sqlite3.Connection:
    """동시 여러 사용자가 접근할 때 쓰기 잠금으로 인한 'database is locked' 오류를 줄이려고
    busy timeout을 기본값(5초)보다 넉넉하게 준다. WAL 모드(읽기가 쓰기를 막지 않음)는
    init_db()에서 DB 파일당 한 번만 설정하면 되므로 여기서 매번 반복하지 않는다."""
    return sqlite3.connect(DB_PATH, timeout=30.0)


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
    content       TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT ''
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


def _ensure_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """table에 column이 없으면 ALTER TABLE로 추가한다 — 스키마에 새 컬럼을 추가했을 때
    이미 존재하는 DB 파일(CREATE TABLE IF NOT EXISTS는 기존 테이블엔 적용되지 않음)도
    함께 마이그레이션되도록 한다."""
    cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as con:
        # WAL 모드에서는 읽기가 쓰기를 막지 않고 쓰기도 읽기를 막지 않는다(쓰기끼리는 여전히
        # 직렬화됨) — 여러 사용자가 동시에 접속할 때 기본 롤백저널 모드보다 잠금 경쟁이 훨씬
        # 적다. DB 파일에 한 번 설정되면 이후 연결에도 유지되므로 매번 다시 설정해도 비용이
        # 거의 없다(이미 WAL이면 no-op).
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_MENTIONS_SQL)
        con.execute(_RUN_LOGS_SQL)
        con.execute(_POLICY_EVENTS_SQL)
        con.execute(_POLICY_RUN_LOGS_SQL)
        _ensure_column(con, "mentions", "summary", "TEXT NOT NULL DEFAULT ''")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mentions_collected_at ON mentions(collected_at)")


def insert_mention(record: dict) -> bool:
    """새 수집 데이터 1건 저장. url이 이미 있으면 False(중복 스킵), 새로 저장되면 True."""
    init_db()
    record = {
        **record,
        "search_term": record.get("search_term", ""),
        "content": record.get("content", ""),
        "summary": record.get("summary", ""),
    }
    with _connect() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO mentions "
            "(brand, channel, source_detail, title, url, snippet, posted_at, collected_at, "
            "search_term, content, summary) "
            "VALUES (:brand, :channel, :source_detail, :title, :url, :snippet, :posted_at, "
            ":collected_at, :search_term, :content, :summary)",
            record,
        )
        return cur.rowcount > 0


def update_mention_summary(mention_id: int, summary: str) -> None:
    """기존 mention 1건의 summary만 갱신한다 (수집 시점에 놓친 건을 뒤늦게 요약해 채울 때 사용)."""
    init_db()
    with _connect() as con:
        con.execute(
            "UPDATE mentions SET summary = :summary WHERE id = :id",
            {"summary": summary, "id": mention_id},
        )


def insert_run_log(entry: dict) -> None:
    init_db()
    entry = {**entry, "run_id": entry.get("run_id", "")}
    with _connect() as con:
        con.execute(
            "INSERT INTO run_logs "
            "(ran_at, trigger, brand, channel, fetched, inserted, skipped, ok, message, run_id) "
            "VALUES (:ran_at, :trigger, :brand, :channel, :fetched, :inserted, :skipped, :ok, :message, :run_id)",
            entry,
        )


def count_mentions() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]


def get_mentions(
    brand: str = "", channel: str = "", channels: list | None = None, limit: int = 3000
) -> list[dict]:
    """channels가 주어지면(빈 리스트 포함) 그 채널들만 대상으로 하고 channel은 무시한다.
    channels=None(기본값)이면 channel 단일 필터만 적용한다(기존 동작과 동일)."""
    init_db()
    if channels is not None and not channels:
        return []
    query = "SELECT * FROM mentions WHERE 1=1"
    params = {"limit": limit}
    if brand:
        query += " AND brand = :brand"
        params["brand"] = brand
    if channels:
        placeholders = ", ".join(f":ch{i}" for i in range(len(channels)))
        query += f" AND channel IN ({placeholders})"
        for i, ch in enumerate(channels):
            params[f"ch{i}"] = ch
    elif channel:
        query += " AND channel = :channel"
        params["channel"] = channel
    query += " ORDER BY collected_at DESC LIMIT :limit"
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_mentions(ids: list[int]) -> int:
    if not ids:
        return 0
    init_db()
    with _connect() as con:
        placeholders = ",".join("?" * len(ids))
        cur = con.execute(f"DELETE FROM mentions WHERE id IN ({placeholders})", ids)
        return cur.rowcount


def delete_all_mentions() -> int:
    init_db()
    with _connect() as con:
        cur = con.execute("DELETE FROM mentions")
        return cur.rowcount


def get_run_logs(limit: int = 50) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM run_logs ORDER BY ran_at DESC LIMIT :limit", {"limit": limit}
        ).fetchall()
        return [dict(r) for r in rows]


_LEGACY_BATCH_GAP_SECONDS = 300


def get_run_batches(limit: int = 50, channels: list[str] | None = None) -> list[dict]:
    """수집 실행을 건바이건이 아니라 run_id 기준 1세트로 묶어서 반환한다.
    channels가 주어지면 그 채널들만 포함된 run_logs 행만 대상으로 한다."""
    init_db()
    query = "SELECT * FROM run_logs"
    params: dict = {}
    if channels:
        placeholders = ", ".join(f":ch{i}" for i in range(len(channels)))
        query += f" WHERE channel IN ({placeholders})"
        params = {f"ch{i}": ch for i, ch in enumerate(channels)}
    query += " ORDER BY ran_at ASC, id ASC LIMIT 2000"

    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(query, params).fetchall()]

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
        run_channels = []
        for r in rows_in_group:
            if r["channel"] not in run_channels:
                run_channels.append(r["channel"])
        messages = [r["message"] for r in rows_in_group if r["message"]]
        batches.append({
            "ran_at": min(r["ran_at"] for r in rows_in_group),
            "trigger": rows_in_group[0]["trigger"],
            "brands": ", ".join(brands),
            "channels": ", ".join(run_channels),
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
    with _connect() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO policy_events "
            "(source, title, url, department, announced_at, view_count, collected_at) "
            "VALUES (:source, :title, :url, :department, :announced_at, :view_count, :collected_at)",
            record,
        )
        return cur.rowcount > 0


def count_policy_events() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM policy_events").fetchone()[0]


def get_policy_events(department: str = "", limit: int = 3000) -> list[dict]:
    init_db()
    query = "SELECT * FROM policy_events WHERE 1=1"
    params = {"limit": limit}
    if department:
        query += " AND department = :department"
        params["department"] = department
    query += " ORDER BY announced_at DESC LIMIT :limit"
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_policy_events(ids: list[int]) -> int:
    """주어진 id들의 정책 이벤트를 삭제. 삭제된 건수를 반환."""
    if not ids:
        return 0
    init_db()
    with _connect() as con:
        placeholders = ",".join("?" * len(ids))
        cur = con.execute(f"DELETE FROM policy_events WHERE id IN ({placeholders})", ids)
        return cur.rowcount


def delete_all_policy_events() -> int:
    """policy_events 테이블의 모든 행을 삭제하고 삭제된 건수를 반환한다."""
    init_db()
    with _connect() as con:
        cur = con.execute("DELETE FROM policy_events")
        return cur.rowcount


def insert_policy_run_log(entry: dict) -> None:
    init_db()
    entry = {**entry, "run_id": entry.get("run_id", "")}
    with _connect() as con:
        con.execute(
            "INSERT INTO policy_run_logs "
            "(ran_at, trigger, source, fetched, inserted, skipped, ok, message, run_id) "
            "VALUES (:ran_at, :trigger, :source, :fetched, :inserted, :skipped, :ok, :message, :run_id)",
            entry,
        )


def get_policy_run_logs(limit: int = 50) -> list[dict]:
    init_db()
    with _connect() as con:
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
    with _connect() as con:
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
