"""
hana_p — SQLite 저장소 (수집 데이터 + 실행 이력)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import sqlite_vec

DB_PATH = Path(__file__).resolve().parent / "data" / "news.db"
VECTOR_DIM = 3072  # gemini-embedding-001 출력 차원


def _connect() -> sqlite3.Connection:
    """동시 여러 사용자가 접근할 때 쓰기 잠금으로 인한 'database is locked' 오류를 줄이려고
    busy timeout을 기본값(5초)보다 넉넉하게 준다. WAL 모드(읽기가 쓰기를 막지 않음)는
    init_db()에서 DB 파일당 한 번만 설정하면 되므로 여기서 매번 반복하지 않는다.
    sqlite-vec 확장을 매 연결마다 로드해서 mention_vectors/policy_vectors 가상 테이블을
    쓸 수 있게 한다 — 로딩 자체는 캐싱된 네이티브 라이브러리를 참조하는 정도라 비용이 작다."""
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    return con


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

_VECTOR_RUN_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS vector_run_logs (
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

_ACTIVITY_LOG_SQL = """
CREATE TABLE IF NOT EXISTS activity_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    ip      TEXT NOT NULL,
    page    TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
"""

_BRIEFING_ARCHIVES_SQL = """
CREATE TABLE IF NOT EXISTS briefing_archives (
    date              TEXT PRIMARY KEY,
    channel_counts    TEXT NOT NULL,
    channel_top_news  TEXT NOT NULL,
    own_brand_news    TEXT NOT NULL,
    competitor_news   TEXT NOT NULL,
    market_news       TEXT NOT NULL,
    total_count       INTEGER NOT NULL,
    archived_at       TEXT NOT NULL
);
"""

def _mention_vectors_sql() -> str:
    # rowid = mentions.id로 맞춰서 JOIN으로 원본 행을 바로 가져올 수 있게 한다. VECTOR_DIM을
    # init_db() 호출 시점에 읽어서, 테스트에서 monkeypatch로 작은 차원을 쓸 수 있게 한다.
    return f"CREATE VIRTUAL TABLE IF NOT EXISTS mention_vectors USING vec0(embedding float[{VECTOR_DIM}])"


def _policy_vectors_sql() -> str:
    return f"CREATE VIRTUAL TABLE IF NOT EXISTS policy_vectors USING vec0(embedding float[{VECTOR_DIM}])"


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
        con.execute(_VECTOR_RUN_LOGS_SQL)
        con.execute(_ACTIVITY_LOG_SQL)
        con.execute(_BRIEFING_ARCHIVES_SQL)
        con.execute(_mention_vectors_sql())
        con.execute(_policy_vectors_sql())
        _ensure_column(con, "mentions", "summary", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "mentions", "embedding", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "policy_events", "embedding", "TEXT NOT NULL DEFAULT ''")
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


def update_mention_embedding(mention_id: int, embedding_json: str) -> None:
    init_db()
    with _connect() as con:
        con.execute(
            "UPDATE mentions SET embedding = :embedding WHERE id = :id",
            {"embedding": embedding_json, "id": mention_id},
        )


def update_policy_event_embedding(event_id: int, embedding_json: str) -> None:
    init_db()
    with _connect() as con:
        con.execute(
            "UPDATE policy_events SET embedding = :embedding WHERE id = :id",
            {"embedding": embedding_json, "id": event_id},
        )


def get_mentions_without_embedding(limit: int = 200) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, title, content, snippet FROM mentions WHERE embedding = '' "
            "ORDER BY id DESC LIMIT :limit", {"limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def get_policy_events_without_embedding(limit: int = 200) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, title, department FROM policy_events WHERE embedding = '' "
            "ORDER BY id DESC LIMIT :limit", {"limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def count_mentions_without_embedding() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM mentions WHERE embedding = ''").fetchone()[0]


def count_policy_events_without_embedding() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM policy_events WHERE embedding = ''").fetchone()[0]


def insert_vector_run_log(entry: dict) -> None:
    init_db()
    entry = {**entry, "run_id": entry.get("run_id", "")}
    with _connect() as con:
        con.execute(
            "INSERT INTO vector_run_logs "
            "(ran_at, trigger, source, fetched, inserted, skipped, ok, message, run_id) "
            "VALUES (:ran_at, :trigger, :source, :fetched, :inserted, :skipped, :ok, :message, :run_id)",
            entry,
        )


def get_vector_run_logs(limit: int = 50) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM vector_run_logs ORDER BY ran_at DESC LIMIT :limit", {"limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def log_activity(ip: str, page: str, action: str, detail: str = "") -> None:
    """접속 IP·페이지·행위를 activity_log에 남긴다 — 관리자 설정 화면의 '로그' 탭에서
    누가(IP) 언제 무엇을(페이지 방문/검색/PDF 생성/AI 채팅/관리 작업 등) 했는지 조회하는 데 쓴다."""
    init_db()
    with _connect() as con:
        con.execute(
            "INSERT INTO activity_log (ts, ip, page, action, detail) "
            "VALUES (:ts, :ip, :page, :action, :detail)",
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": ip, "page": page, "action": action, "detail": detail,
            },
        )


def get_activity_log(limit: int = 500, ip: str = "") -> list[dict]:
    init_db()
    query = "SELECT * FROM activity_log WHERE 1=1"
    params = {"limit": limit}
    if ip:
        query += " AND ip = :ip"
        params["ip"] = ip
    query += " ORDER BY id DESC LIMIT :limit"
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def count_activity_log() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]


def distinct_activity_ips() -> list[str]:
    init_db()
    with _connect() as con:
        return [row[0] for row in con.execute("SELECT DISTINCT ip FROM activity_log ORDER BY ip")]


def _upsert_vector(con: sqlite3.Connection, table: str, rowid: int, embedding: list[float]) -> None:
    """vec0 가상 테이블은 rowid 충돌에 대해 INSERT OR REPLACE를 지원하지 않아서
    DELETE 후 INSERT로 upsert한다."""
    con.execute(f"DELETE FROM {table} WHERE rowid = ?", [rowid])
    con.execute(
        f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
        [rowid, sqlite_vec.serialize_float32(embedding)],
    )


def upsert_mention_vector(mention_id: int, embedding: list[float]) -> None:
    init_db()
    with _connect() as con:
        _upsert_vector(con, "mention_vectors", mention_id, embedding)


def upsert_policy_vector(event_id: int, embedding: list[float]) -> None:
    init_db()
    with _connect() as con:
        _upsert_vector(con, "policy_vectors", event_id, embedding)


def search_mention_vectors(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """질의 임베딩과 가장 가까운 mentions 상위 top_k건을 거리 오름차순(가까운 순)으로 반환한다.
    아직 색인된 벡터가 없으면 빈 리스트를 반환한다."""
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT m.*, v.distance AS distance FROM mention_vectors v "
            "JOIN mentions m ON m.id = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? "
            "ORDER BY v.distance",
            [sqlite_vec.serialize_float32(query_embedding), top_k],
        ).fetchall()
        return [dict(r) for r in rows]


def search_policy_vectors(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT p.*, v.distance AS distance FROM policy_vectors v "
            "JOIN policy_events p ON p.id = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? "
            "ORDER BY v.distance",
            [sqlite_vec.serialize_float32(query_embedding), top_k],
        ).fetchall()
        return [dict(r) for r in rows]


def count_mention_vector_index() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM mention_vectors").fetchone()[0]


def count_policy_vector_index() -> int:
    init_db()
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM policy_vectors").fetchone()[0]


def get_mentions_missing_vector_index(limit: int = 1000) -> list[dict]:
    """embedding은 이미 만들어졌지만(mentions.embedding) 아직 mention_vectors 색인에는
    들어가지 않은 행 — 색인 테이블이 새로 추가되기 전에 이미 벡터화된 데이터를
    백필하거나(sync_vector_index), 색인이 유실된 경우를 복구하는 데 쓴다."""
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, embedding FROM mentions WHERE embedding != '' "
            "AND id NOT IN (SELECT rowid FROM mention_vectors) LIMIT :limit",
            {"limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def get_policy_events_missing_vector_index(limit: int = 1000) -> list[dict]:
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, embedding FROM policy_events WHERE embedding != '' "
            "AND id NOT IN (SELECT rowid FROM policy_vectors) LIMIT :limit",
            {"limit": limit},
        ).fetchall()
        return [dict(r) for r in rows]


def insert_briefing_archive(record: dict) -> bool:
    """하루치 브리핑을 확정해 저장한다. 이미 그 날짜가 있으면 아무 것도 하지 않고 False —
    한 번 확정된 브리핑은 이후 채널 노출 설정이나 원본 데이터 변경과 무관하게 고정된다."""
    init_db()
    with _connect() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO briefing_archives "
            "(date, channel_counts, channel_top_news, own_brand_news, competitor_news, "
            "market_news, total_count, archived_at) "
            "VALUES (:date, :channel_counts, :channel_top_news, :own_brand_news, "
            ":competitor_news, :market_news, :total_count, :archived_at)",
            {
                "date": record["date"],
                "channel_counts": json.dumps(record["channel_counts"], ensure_ascii=False),
                "channel_top_news": json.dumps(record["channel_top_news"], ensure_ascii=False),
                "own_brand_news": json.dumps(record["own_brand_news"], ensure_ascii=False),
                "competitor_news": json.dumps(record["competitor_news"], ensure_ascii=False),
                "market_news": json.dumps(record["market_news"], ensure_ascii=False),
                "total_count": record["total_count"],
                "archived_at": record["archived_at"],
            },
        )
        return cur.rowcount > 0


def get_briefing_archive(date: str) -> dict | None:
    """확정된 하루치 브리핑을 반환한다. 아직 확정 안 됐으면 None."""
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM briefing_archives WHERE date = ?", [date]).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ("channel_counts", "channel_top_news", "own_brand_news", "competitor_news", "market_news"):
            result[key] = json.loads(result[key])
        return result


def get_archived_briefing_dates() -> set[str]:
    init_db()
    with _connect() as con:
        rows = con.execute("SELECT date FROM briefing_archives").fetchall()
        return {r[0] for r in rows}


def get_earliest_mention_date() -> str | None:
    init_db()
    with _connect() as con:
        row = con.execute("SELECT MIN(date(collected_at)) FROM mentions").fetchone()
        return row[0] if row and row[0] else None


def get_mentions_by_collected_date(date: str) -> list[dict]:
    """채널 표시 설정과 무관하게 그 날짜에 수집된 mentions 전체를 반환한다 — 브리핑
    아카이빙은 확정 시점의 전체 채널 데이터를 기준으로 해야 하므로 get_mentions()의
    노출 필터를 거치지 않는다."""
    init_db()
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM mentions WHERE date(collected_at) = ? ORDER BY collected_at DESC", [date]
        ).fetchall()
        return [dict(r) for r in rows]
