# 정부 정책 데이터 수집 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MarketInsight(자매 프로젝트)에 이미 검증된 "정부 정책(공공기관 보도자료)" 7개 소스 수집
기능을 hana_p에 그대로 이식한다 — 기존 브랜드×채널 수집과 완전히 분리된 별도 테이블/로직/
UI로 추가한다.

**Architecture:** MarketInsight의 `crawlers/{molit,reb,lh,seoul_opengov,hf,hug,sh}.py`,
`db.py`의 `policy_events`/`policy_run_logs` 테이블, `collector.py`의 정책 전용 수집·백그라운드
스레드 로직, `scheduler.py`의 정책 전용 자동 틱을 원본 그대로 복사해 hana_p 구조(단일
`views/settings.py` 관리자 페이지, 탭 기반 UI)에 맞춰 배선한다. 브랜드 수집(mentions/run_logs,
`_active_run_id` 등)과 상태·락·테이블을 전혀 공유하지 않는다.

**Tech Stack:** Python, Streamlit, SQLite(sqlite3), requests, beautifulsoup4, pytest(신규 도입).

## Global Constraints

- 신규 pip 의존성은 `pytest>=8.0.0` 하나뿐(크롤러는 기존 requests/beautifulsoup4만 사용).
- 모든 정책 관련 위젯 `key`는 `policy_` 접두어를 사용해 브랜드용 key와 절대 겹치지 않게 한다.
- `policy_events`/`policy_run_logs`는 `mentions`/`run_logs`와 완전히 분리된 테이블 — 정책 삭제
  함수가 브랜드 데이터를 절대 건드리지 않아야 한다(각 태스크의 테스트로 검증).
- 각 크롤러 `fetch_press_releases(start, end)`는 네트워크 오류/구조 변경 시 예외를 삼키고
  빈 리스트를 반환한다 — 이 계약을 깨면 안 된다.
- UI 태스크(12, 13)는 자동 테스트 하네스가 없는 hana_p의 기존 `views/settings.py` 관례를
  따라 자동 테스트 없이 수동 실행(`streamlit run app.py`)으로 검증한다.

---

### Task 0: pytest 인프라 도입

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py` (빈 파일 — 패키지 인식용, MarketInsight에는 없지만 `import tests...`
  형태를 쓰지 않으므로 실제로는 불필요. **생성하지 않는다** — conftest.py의 sys.path 조작만으로
  충분하다. 이 항목은 착오 방지를 위해 명시적으로 "만들지 않음"을 기록한다.)
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `tests/conftest.py`가 프로젝트 루트를 `sys.path`에 넣어 이후 모든 테스트 파일에서
  `import db`, `import collector`, `import scheduler`, `from crawlers import molit` 등 최상위
  모듈을 바로 import할 수 있게 한다.

- [ ] **Step 1: `requirements.txt`에 pytest 추가**

`requirements.txt` 끝에 한 줄 추가:

```
pytest>=8.0.0
```

- [ ] **Step 2: pytest 설치**

Run: `pip install -r requirements.txt`
Expected: `pytest`가 설치됨 (이미 설치된 다른 패키지는 변화 없음)

- [ ] **Step 3: `tests/conftest.py` 작성**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: 빈 테스트 스위트가 정상 수집되는지 확인**

Run: `pytest tests/ -v`
Expected: `no tests ran` (수집 오류 없이 종료 — `ModuleNotFoundError` 등이 없어야 함)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/conftest.py
git commit -m "test: add pytest infrastructure"
```

---

### Task 1: `utils.py` — 정책 전용 수집 스케줄 설정

**Files:**
- Modify: `utils.py`
- Create: `tests/test_utils.py`

**Interfaces:**
- Consumes: `utils.load_json`, `utils.save_json`, `utils._normalize_schedule_times`(기존 함수,
  변경 없음)
- Produces: `utils.POLICY_COLLECTION_SCHEDULE_FILE: Path`,
  `utils.load_policy_collection_schedule() -> dict`(`{"times": [...]}`),
  `utils.save_policy_collection_schedule(cfg: dict) -> None` — Task 11(scheduler)과
  Task 12(UI)가 그대로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_utils.py` 새로 생성:

```python
import json
from datetime import datetime

from utils import (
    load_collection_schedule,
    load_policy_collection_schedule,
    resolve_relative_korean_date,
    save_collection_schedule,
    save_policy_collection_schedule,
)
import utils


def test_load_policy_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )

    assert load_policy_collection_schedule() == {"times": []}


def test_save_policy_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "policy_collection_schedule.json"
    monkeypatch.setattr(utils, "POLICY_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_policy_collection_schedule({"times": ["10:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["10:00"]}


def test_policy_collection_schedule_is_independent_of_brand_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "COLLECTION_SCHEDULE_FILE", tmp_path / "collection_schedule.json")
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )

    save_collection_schedule({"times": ["09:00"]})
    save_policy_collection_schedule({"times": ["10:00"]})

    assert load_collection_schedule() == {"times": ["09:00"]}
    assert load_policy_collection_schedule() == {"times": ["10:00"]}


def test_resolve_relative_korean_date_still_works():
    now = datetime(2026, 7, 24, 12, 0, 0)
    assert resolve_relative_korean_date("30분 전", now) == "2026.07.24"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_utils.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_policy_collection_schedule'`

- [ ] **Step 3: `utils.py`에 정책 스케줄 함수 추가**

`utils.py`의 `COLLECTION_SCHEDULE_FILE = DATA_DIR / "collection_schedule.json"` 바로 아래에
추가:

```python
POLICY_COLLECTION_SCHEDULE_FILE = DATA_DIR / "policy_collection_schedule.json"
```

`save_collection_schedule` 함수 바로 아래(`_RELATIVE_KOREAN_DATE_RE` 정의 이전)에 추가:

```python
def load_policy_collection_schedule() -> dict:
    cfg = load_json(POLICY_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_policy_collection_schedule(cfg: dict) -> None:
    save_json(POLICY_COLLECTION_SCHEDULE_FILE, cfg)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_utils.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat: add policy collection schedule config"
```

---

### Task 2: `db.py` — `policy_events` / `policy_run_logs` 테이블

**Files:**
- Modify: `db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: 없음(신규 테이블, 기존 `mentions`/`run_logs`와 무관)
- Produces: `db.insert_policy_event(record: dict) -> bool`,
  `db.get_policy_events(department: str = "") -> list[dict]`,
  `db.delete_policy_events(ids: list[int]) -> int`,
  `db.delete_all_policy_events() -> int`,
  `db.insert_policy_run_log(entry: dict) -> None`,
  `db.get_policy_run_logs(limit: int = 50) -> list[dict]`,
  `db.get_policy_run_batches(limit: int = 50) -> list[dict]` — Task 10(collector)과
  Task 13(UI)이 그대로 사용한다. 레코드 dict 필드: `source, title, url, department,
  announced_at, view_count, collected_at`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_db.py` 새로 생성:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'insert_policy_event'`

- [ ] **Step 3: `db.py`에 테이블/함수 추가**

`db.py`의 `_RUN_LOGS_SQL` 정의 바로 아래에 추가:

```python
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
```

`init_db()`를 다음으로 교체(정책 테이블 생성 추가):

```python
def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(_MENTIONS_SQL)
        con.execute(_RUN_LOGS_SQL)
        con.execute(_POLICY_EVENTS_SQL)
        con.execute(_POLICY_RUN_LOGS_SQL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mentions_collected_at ON mentions(collected_at)")
```

파일 끝(`get_run_batches` 함수 뒤)에 추가:

```python
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


def get_policy_events(department: str = "") -> list[dict]:
    init_db()
    query = "SELECT * FROM policy_events WHERE 1=1"
    params = {}
    if department:
        query += " AND department = :department"
        params["department"] = department
    query += " ORDER BY announced_at DESC"
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_db.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add policy_events and policy_run_logs tables"
```

---

### Task 3: `crawlers/molit.py` — 국토교통부 보도자료

**Files:**
- Create: `crawlers/molit.py`
- Create: `tests/test_crawler_molit.py`

**Interfaces:**
- Produces: `molit.fetch_press_releases(start: date, end: date) -> list[dict]` — 각 dict는
  `{"title", "url", "department", "announced_at", "view_count"}`. Task 10(collector)이 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_molit.py`:

```python
from datetime import date

from crawlers import molit

_SAMPLE_HTML = """
<table class="table line_no bd_tbl bd_tbl_ul">
  <tr><th>번호</th><th>제목</th><th>분류</th><th>등록일</th><th>조회수</th></tr>
  <tr>
    <td>834</td>
    <td><a href="dtl.jsp?lcmspage=1&id=95092253">스마트도시산업 통계 특수분류 제정</a></td>
    <td>국토도시</td>
    <td>2026-07-24</td>
    <td>512</td>
  </tr>
  <tr>
    <td>833</td>
    <td><a href="dtl.jsp?lcmspage=1&id=95092252">’26년 상반기 전국 지가 1.22% 상승</a></td>
    <td>주택토지</td>
    <td>2026-07-23</td>
    <td>836</td>
  </tr>
</table>
"""


def test_fetch_press_releases_parses_title_url_department_date_and_views(monkeypatch):
    class FakeResponse:
        text = _SAMPLE_HTML

        def raise_for_status(self):
            pass

    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(molit.requests, "get", fake_get)

    results = molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24))

    assert captured["url"] == "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
    assert captured["params"]["search_regdate_s"] == "2026-06-24"
    assert captured["params"]["search_regdate_e"] == "2026-07-24"
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "스마트도시산업 통계 특수분류 제정"
    assert first["url"] == "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?lcmspage=1&id=95092253"
    assert first["department"] == "국토도시"
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 512


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise molit.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(molit.requests, "get", fake_get)

    assert molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(molit.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert molit.fetch_press_releases(date(2026, 6, 24), date(2026, 7, 24)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_molit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.molit'`

- [ ] **Step 3: `crawlers/molit.py` 작성**

```python
"""
hana_p — 국토교통부 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """국토교통부 보도자료 목록을 start~end 날짜 범위로 한 번에 가져온다. 네트워크 오류나
    페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체 수집 과정을
    중단시키면 안 된다."""
    try:
        resp = requests.get(
            _LIST_URL,
            params={
                "psize": 100,
                "search_regdate_s": start.isoformat(),
                "search_regdate_e": end.isoformat(),
                "lcmspage": 1,
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.select_one("table.bd_tbl")
        if table is None:
            return []

        results = []
        for tr in table.select("tr"):
            tds = tr.select("td")
            if len(tds) != 5:
                continue
            link = tds[1].select_one("a")
            if link is None:
                continue
            title = link.get_text(strip=True)
            url = urljoin(_LIST_URL, link["href"])
            department = tds[2].get_text(strip=True)
            announced_at = tds[3].get_text(strip=True)
            try:
                view_count = int(tds[4].get_text(strip=True))
            except ValueError:
                view_count = 0
            results.append({
                "title": title,
                "url": url,
                "department": department,
                "announced_at": announced_at,
                "view_count": view_count,
            })
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_molit.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/molit.py tests/test_crawler_molit.py
git commit -m "feat: add MOLIT press release crawler"
```

---

### Task 4: `crawlers/reb.py` — 한국부동산원 보도자료

**Files:**
- Create: `crawlers/reb.py`
- Create: `tests/test_crawler_reb.py`

**Interfaces:**
- Produces: `reb.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_reb.py`:

```python
from datetime import date

from crawlers import reb

_PAGE1_HTML = """
<table>
  <thead><tr><th>번호</th><th>제목</th><th>등록일</th><th>조회</th><th>첨부</th></tr></thead>
  <tbody>
    <tr>
      <td>1910</td>
      <td class="al mBlock"><a href="javascript:" data-id="115796" class="nttInfoBtn">
        한국부동산원, 한국토지보상법연구회와 공동 학술세미나 개최</a></td>
      <td>2026.07.27.</td>
      <td>4</td>
      <td></td>
    </tr>
    <tr>
      <td>1909</td>
      <td class="al mBlock"><a href="javascript:" data-id="115757" class="nttInfoBtn">
        주간아파트가격동향(20260720기준)</a></td>
      <td>2026.07.23.</td>
      <td>1958</td>
      <td></td>
    </tr>
  </tbody>
</table>
"""

_PAGE2_HTML = """
<table>
  <thead><tr><th>번호</th><th>제목</th><th>등록일</th><th>조회</th><th>첨부</th></tr></thead>
  <tbody>
    <tr>
      <td>1900</td>
      <td class="al mBlock"><a href="javascript:" data-id="114918" class="nttInfoBtn">
        오래된 보도자료</a></td>
      <td>2026.06.01.</td>
      <td>10</td>
      <td></td>
    </tr>
  </tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_date_and_views(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured.setdefault("calls", []).append(data["currPage"])
        captured["url"] = url
        captured["data"] = data

        class FakeResponse:
            text = _PAGE1_HTML if data["currPage"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(reb.requests, "post", fake_post)

    results = reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.reb.or.kr/reb/na/ntt/selectNttList.do"
    assert captured["data"]["mi"] == "9565"
    assert captured["data"]["bbsId"] == "1154"
    assert captured["calls"][0] == 1
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "한국부동산원, 한국토지보상법연구회와 공동 학술세미나 개최"
    assert first["url"] == (
        "https://www.reb.or.kr/reb/na/ntt/selectNttInfo.do?mi=9565&bbsId=1154&nttSn=115796"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-27"
    assert first["view_count"] == 4


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_post(url, data, headers, timeout):
        class FakeResponse:
            text = pages[data["currPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(reb.requests, "post", fake_post)

    results = reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_post(url, data, headers, timeout):
        raise reb.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(reb.requests, "post", fake_post)

    assert reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(reb.requests, "post", lambda url, data, headers, timeout: FakeResponse())

    assert reb.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_reb.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.reb'`

- [ ] **Step 3: `crawlers/reb.py` 작성**

```python
"""
hana_p — 한국부동산원(REB) 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.reb.or.kr/reb/na/ntt/selectNttList.do"
_DETAIL_URL = "https://www.reb.or.kr/reb/na/ntt/selectNttInfo.do"
_MI = "9565"
_BBS_ID = "1154"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 게시판 페이지가 오래된 글까지 무한히 이어지므로, start 날짜에 도달하면 멈추되
# 혹시 모를 무한 루프를 막기 위한 안전장치로 최대 페이지 수를 둔다.
_MAX_PAGES = 50


def _to_iso_date(raw: str) -> str:
    """'2026.07.27.' 형식을 '2026-07-27'로 변환한다."""
    parts = [p for p in raw.strip().rstrip(".").split(".") if p]
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _fetch_page(page: int) -> str:
    resp = requests.post(
        _LIST_URL,
        data={
            "currPage": page,
            "listUseAt": "Y", "replyAt": "N", "cvplAt": "N", "nttCnChk": "N",
            "sysId": "reb", "mberId": "", "bbsTy": "CUSTOM", "customId": "NesDta",
            "resveInsertAt": "N", "newHour": "24", "cmmnCode": "ctgryBbs1105",
            "replyDtAt": "N", "maxSn": "10", "noticeAt": "N", "nttOrdr": "regdt",
            "answerTy": "N", "mi": _MI, "useAt": "Y", "minSn": "0",
            "bbsId": _BBS_ID, "ctgryBbs": "Y", "readyNttMber": "Y",
        },
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """한국부동산원 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을
    만나면 멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 —
    이 함수의 실패가 전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            soup = BeautifulSoup(_fetch_page(page), "html.parser")
            rows = soup.select("table tbody tr")
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a.nttInfoBtn")
                tds = tr.find_all("td")
                if title_a is None or len(tds) < 4:
                    continue
                ntt_sn = title_a.get("data-id", "")
                title = title_a.get_text(strip=True)
                announced_at = _to_iso_date(tds[2].get_text(strip=True))
                if not ntt_sn or not title or not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                try:
                    view_count = int(tds[3].get_text(strip=True))
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title,
                    "url": f"{_DETAIL_URL}?mi={_MI}&bbsId={_BBS_ID}&nttSn={ntt_sn}",
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_reb.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/reb.py tests/test_crawler_reb.py
git commit -m "feat: add REB press release crawler"
```

---

### Task 5: `crawlers/lh.py` — LH(한국토지주택공사) 보도자료

**Files:**
- Create: `crawlers/lh.py`
- Create: `tests/test_crawler_lh.py`

**Interfaces:**
- Produces: `lh.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_lh.py`:

```python
from datetime import date

from crawlers import lh

_PAGE1_HTML = """
<div class="blog_box">
	<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077">
		<div class="desc">
			<strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
			<span class="date">2026-07-24</span>
		</div>
	</a>
</div>
<div class="board_list">
	<ul class="gallery_list type1">
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12072">
				<span class="desc">
					<strong class="title">신축매입임대 자금조달 부담 완화 등 전면 시행</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-07-20</span>
				</span>
			</a>
		</li>
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12069">
				<span class="desc">
					<strong class="title">한국토지주택공사(LH), 광명시흥 공공주택지구 보상 착수</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-07-14</span>
				</span>
			</a>
		</li>
	</ul>
</div>
"""

_PAGE2_HTML = """
<div class="blog_box">
	<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077">
		<div class="desc">
			<strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
			<span class="date">2026-07-24</span>
		</div>
	</a>
</div>
<div class="board_list">
	<ul class="gallery_list type1">
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=11999">
				<span class="desc">
					<strong class="title">오래된 보도자료</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-06-01</span>
				</span>
			</a>
		</li>
	</ul>
</div>
"""


def test_fetch_press_releases_parses_title_url_date_and_skips_featured_duplicate(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("pages", []).append(params["nPage"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["nPage"] == 1 else "<div></div>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.lh.or.kr/gallery.es"
    assert captured["pages"][0] == 1
    assert len(results) == 3
    first = results[0]
    assert first["title"] == "한국토지주택공사(LH), 2026년 기업설명회(IR) 개최"
    assert first["url"] == (
        "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 0


def test_fetch_press_releases_stops_paging_once_older_than_start_without_featured_tripping_it(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["nPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 3
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_normalizes_featured_item_url_across_pages(monkeypatch):
    """실사이트에서 featured 항목의 href는 nPage/vlist_no_npage 등 '현재 조회 중인 페이지'를
    반영해 페이지마다 querystring이 달라진다 (프로덕션 DB에서 중복 저장으로 확인된 버그) —
    list_no만으로 URL을 재구성해 페이지에 관계없이 항상 같은 URL이 나와야 한다."""
    page1 = """
    <div class="blog_box">
        <a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12077&nPage=1&vlist_no_npage=0&keyField=&orderby=">
            <div class="desc">
                <strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
                <span class="date">2026-07-24</span>
            </div>
        </a>
    </div>
    <div class="board_list"><ul class="gallery_list type1">
        <li><a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12072&nPage=1&vlist_no_npage=1&keyField=&orderby=">
            <span class="desc"><strong class="title">신축매입임대 자금조달 부담 완화</strong>
            <span class="date"><strong class="label">등록일</strong> 2026-07-20</span></span>
        </a></li>
    </ul></div>
    """
    page2 = """
    <div class="blog_box">
        <a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12077&nPage=2&vlist_no_npage=0&keyField=&orderby=">
            <div class="desc">
                <strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
                <span class="date">2026-07-24</span>
            </div>
        </a>
    </div>
    <div class="board_list"><ul class="gallery_list type1">
        <li><a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=11999&nPage=2&vlist_no_npage=1&keyField=&orderby=">
            <span class="desc"><strong class="title">오래된 보도자료</strong>
            <span class="date"><strong class="label">등록일</strong> 2026-06-01</span></span>
        </a></li>
    </ul></div>
    """
    pages = [page1, page2]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["nPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    featured_urls = [r["url"] for r in results if r["title"].endswith("기업설명회(IR) 개최")]
    assert featured_urls == [
        "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077"
    ]


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise lh.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(lh.requests, "get", fake_get)

    assert lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_board_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(lh.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_lh.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.lh'`

- [ ] **Step 3: `crawlers/lh.py` 작성**

```python
"""
hana_p — LH(한국토지주택공사) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.lh.or.kr/gallery.es"
_MID = "a10502000000"
_BID = "0003"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 게시판이 오래된 글까지 무한히 이어지므로, start 날짜에 도달하면 멈추되 혹시 모를
# 무한 루프를 막기 위한 안전장치로 최대 페이지 수를 둔다.
_MAX_PAGES = 50
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LIST_NO_RE = re.compile(r"list_no=(\d+)")


def _parse_item(a) -> dict | None:
    title_el = a.select_one("strong.title")
    date_el = a.select_one("span.date")
    href = a.get("href", "")
    if title_el is None or date_el is None or not href:
        return None
    date_match = _DATE_RE.search(date_el.get_text(" ", strip=True))
    list_no_match = _LIST_NO_RE.search(href)
    if not date_match or not list_no_match:
        return None
    return {
        "title": title_el.get_text(strip=True),
        # href의 nPage/vlist_no_npage 등은 "현재 보고 있는 목록 페이지"를 반영해 조회할 때마다
        # 값이 달라진다 — list_no만으로 상세 URL을 직접 구성해야 같은 글이 항상 같은 URL이 되고,
        # DB의 URL UNIQUE 제약으로 정상적으로 중복 방지된다 (nPage를 그대로 쓰면 페이지마다
        # URL이 달라져 같은 글이 중복 저장됨 — 실제로 프로덕션 DB에서 확인된 버그).
        "url": f"{_LIST_URL}?mid={_MID}&bid={_BID}&act=view&list_no={list_no_match.group(1)}",
        "announced_at": date_match.group(),
    }


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """LH 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 맨 위 'blog_box' 특집 항목은 페이지마다 반복 노출되고 정렬 순서를 따르지
    않으므로, 이 항목 때문에 페이지네이션이 조기 중단되지 않도록 따로 취급한다.
    네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가
    전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        seen_urls = set()
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL,
                params={"mid": _MID, "bid": _BID, "nPage": page},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            featured_a = soup.select_one(".blog_box a")
            list_as = soup.select(".board_list .gallery_list li a")
            if featured_a is None and not list_as:
                break

            reached_start = False
            for a, is_featured in [(featured_a, True)] + [(x, False) for x in list_as]:
                if a is None:
                    continue
                item = _parse_item(a)
                if item is None or item["url"] in seen_urls:
                    continue
                if item["announced_at"] < start.isoformat():
                    if is_featured:
                        continue
                    reached_start = True
                    break
                if item["announced_at"] > end.isoformat():
                    continue
                seen_urls.add(item["url"])
                results.append({
                    "title": item["title"],
                    "url": item["url"],
                    "department": "",
                    "announced_at": item["announced_at"],
                    "view_count": 0,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_lh.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/lh.py tests/test_crawler_lh.py
git commit -m "feat: add LH press release crawler"
```

---

### Task 6: `crawlers/seoul_opengov.py` — 서울시 정보소통광장 보도자료

**Files:**
- Create: `crawlers/seoul_opengov.py`
- Create: `tests/test_crawler_seoul_opengov.py`

**Interfaces:**
- Produces: `seoul_opengov.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_seoul_opengov.py`:

```python
from datetime import date

from crawlers import seoul_opengov

_PAGE1_HTML = """
<table>
<thead><tr><th>번호</th><th>제목</th><th>부서</th><th>등록일</th><th>조회</th></tr></thead>
<tbody>
<tr>
    <td class="data-num">46038</td>
    <td class="data-title aLeft"><a href="/press/36601374">제14차정비사업통합심의위원회개최결과</a></td>
    <td class="data-dept">주택실주거정비과</td>
    <td class="data-date">2026-07-24</td>
    <td class="data-hit">46</td>
</tr>
<tr>
    <td class="data-num">46036</td>
    <td class="data-title aLeft"><a href="/press/36601376">상담사지키고상담품질높인다</a></td>
    <td class="data-dept">서울시120다산콜재단</td>
    <td class="data-date">2026-07-24</td>
    <td class="data-hit">24</td>
</tr>
</tbody>
</table>
"""

_PAGE2_HTML = """
<table>
<tbody>
<tr>
    <td class="data-num">46000</td>
    <td class="data-title aLeft"><a href="/press/36500000">오래된주택정책보도자료</a></td>
    <td class="data-dept">주택실주택정책과</td>
    <td class="data-date">2026-06-01</td>
    <td class="data-hit">5</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_keeps_only_relevant_departments(monkeypatch):
    def fake_get(url, params, headers, timeout):
        captured.setdefault("calls", []).append(params["page"])

        class FakeResponse:
            text = _PAGE1_HTML if params["page"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    captured = {}
    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    results = seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 1
    first = results[0]
    assert first["title"] == "제14차정비사업통합심의위원회개최결과"
    assert first["url"] == "https://opengov.seoul.go.kr/press/36601374"
    assert first["department"] == "주택실주거정비과"
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 46


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["page"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    results = seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 1
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise seoul_opengov.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(seoul_opengov.requests, "get", fake_get)

    assert seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        seoul_opengov.requests, "get", lambda url, params, headers, timeout: FakeResponse()
    )

    assert seoul_opengov.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_seoul_opengov.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.seoul_opengov'`

- [ ] **Step 3: `crawlers/seoul_opengov.py` 작성**

```python
"""
hana_p — 서울시 정보소통광장 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://opengov.seoul.go.kr/press/list"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MAX_PAGES = 50
# 서울시 보도자료는 시정 전반(교육/문화/복지 등)을 다루므로, 부동산/주택 정책과 무관한
# 부서 게시물이 대부분이다 — 부서명에 이 키워드 중 하나라도 포함된 게시물만 남긴다.
# "도시"만 넣으면 "도시외교", "도시브랜드" 등 무관한 부서까지 걸려 "도시공간본부"처럼
# 더 구체적인 형태로 좁혔다 — 다른 부동산 관련 부서가 나타나면 추가할 것.
_RELEVANT_DEPT_KEYWORDS = ["주택", "도시공간본부", "정비", "재건축", "재개발", "건축"]


def _is_relevant_department(department: str) -> bool:
    return any(kw in department for kw in _RELEVANT_DEPT_KEYWORDS)


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """서울시 정보소통광장 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 주택/도시계획 관련 부서 게시물만 남기고 나머지 시정 전반 게시물은 걸러낸다.
    네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체
    수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL,
                params={"page": page, "items_per_page": 50},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            rows = [tr for tr in rows if tr.select_one("td.data-title a")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("td.data-title a")
                date_td = tr.select_one("td.data-date")
                dept_td = tr.select_one("td.data-dept")
                if title_a is None or date_td is None:
                    continue
                announced_at = date_td.get_text(strip=True)
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                department = dept_td.get_text(strip=True) if dept_td else ""
                if not _is_relevant_department(department):
                    continue
                hit_td = tr.select_one("td.data-hit")
                try:
                    view_count = int(hit_td.get_text(strip=True)) if hit_td else 0
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": urljoin(_LIST_URL, title_a["href"]),
                    "department": department,
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_seoul_opengov.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/seoul_opengov.py tests/test_crawler_seoul_opengov.py
git commit -m "feat: add Seoul opengov press release crawler"
```

---

### Task 7: `crawlers/hf.py` — 한국주택금융공사(HF) 보도자료

**Files:**
- Create: `crawlers/hf.py`
- Create: `tests/test_crawler_hf.py`

**Interfaces:**
- Produces: `hf.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_hf.py`:

```python
from datetime import date

from crawlers import hf

_PAGE1_HTML = """
<table class="board-table">
<tbody>
<tr class="">
    <td class="b-num-box">2389</td>
    <td class="b-td-left">
        <div class="b-title-box">
            <a data-article-no="600383" href="?mode=view&amp;articleNo=600383&amp;article.offset=0&amp;articleLimit=10">
                주택금융공사, 초록우산어린이재단에 후원금 전달
            </a>
            <div class="b-m-con">
                <span class="b-date">2026-07-24</span>
                <span class="hit">조회수 97</span>
            </div>
        </div>
    </td>
    <td>2026-07-24</td>
    <td class="">97</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_date_and_views(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("offsets", []).append(params["article.offset"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["article.offset"] == 0 else "<table class=\"board-table\"></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hf.requests, "get", fake_get)

    results = hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
    assert captured["offsets"][0] == 0
    assert len(results) == 1
    first = results[0]
    assert first["title"] == "주택금융공사, 초록우산어린이재단에 후원금 전달"
    assert first["url"] == (
        "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
        "?mode=view&articleNo=600383&article.offset=0&articleLimit=10"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 97


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise hf.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(hf.requests, "get", fake_get)

    assert hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(hf.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert hf.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_hf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.hf'`

- [ ] **Step 3: `crawlers/hf.py` 작성**

```python
"""
hana_p — 한국주택금융공사(HF) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.hf.go.kr/_custom/hf/_common/board/index/21.do"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_PAGE_SIZE = 10
_MAX_PAGES = 50
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_VIEW_COUNT_RE = re.compile(r"조회수\s*(\d+)")


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """HF 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의
    실패가 전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_SIZE
            resp = requests.get(
                _LIST_URL,
                params={"mode": "list", "article.offset": offset, "articleLimit": _PAGE_SIZE},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table.board-table tr")
            rows = [tr for tr in rows if tr.select_one("a[data-article-no]")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a[data-article-no]")
                row_text = tr.get_text(" ", strip=True)
                date_match = _DATE_RE.search(row_text)
                if title_a is None or date_match is None:
                    continue
                announced_at = date_match.group()
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                view_match = _VIEW_COUNT_RE.search(row_text)
                view_count = int(view_match.group(1)) if view_match else 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": urljoin(_LIST_URL, title_a["href"]),
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_hf.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/hf.py tests/test_crawler_hf.py
git commit -m "feat: add HF press release crawler"
```

---

### Task 8: `crawlers/hug.py` — 주택도시보증공사(HUG) 보도자료

**Files:**
- Create: `crawlers/hug.py`
- Create: `tests/test_crawler_hug.py`

**Interfaces:**
- Produces: `hug.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_hug.py`:

```python
from datetime import date

from crawlers import hug

_ROW1 = """
<tr>
    <td><a href="hsnd000002.jsp?idx=38054"><span class="ico-new"><em class="hide">최근 게시물</em></span>
        부산지역 주거·의료 취약 아동 위한 사업 참여가정 모집</a></td>
    <td>2026.07.27</td>
</tr>
"""
_ROW2 = """
<tr>
    <td><a href="hsnd000002.jsp?idx=38047">AI감사 전문성 강화를 위해 업무협약 체결</a></td>
    <td>2026.07.23</td>
</tr>
"""
_ROW_OLD = """
<tr>
    <td><a href="hsnd000002.jsp?idx=30000">오래된 보도자료</a></td>
    <td>2026.06.01</td>
</tr>
"""


def _table(*rows):
    return f'<table class="tbl-style02"><tbody>{"".join(rows)}</tbody></table>'


def test_fetch_press_releases_parses_title_url_date_and_strips_new_badge(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured.setdefault("row_sizes", []).append(data["rowSize"])
        captured["url"] = url

        class FakeResponse:
            text = _table(_ROW1, _ROW2)
            encoding = "utf-8"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hug.requests, "post", fake_post)

    results = hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000001.jsp"
    assert captured["row_sizes"][0] == 20
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "부산지역 주거·의료 취약 아동 위한 사업 참여가정 모집"
    assert first["url"] == "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000002.jsp?idx=38054"
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-27"
    assert first["view_count"] == 0
    assert results[1]["title"] == "AI감사 전문성 강화를 위해 업무협약 체결"


def test_fetch_press_releases_only_processes_newly_added_rows_across_calls(monkeypatch):
    """rowSize를 늘려도 응답은 처음부터 누적된 전체 목록이므로, 이미 처리한 행을
    다시 처리하면 안 된다."""
    responses = [_table(_ROW1, _ROW2), _table(_ROW1, _ROW2, _ROW_OLD)]

    def fake_post(url, data, headers, timeout):
        idx = 0 if data["rowSize"] == 20 else 1

        class FakeResponse:
            text = responses[idx]
            encoding = "utf-8"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(hug.requests, "post", fake_post)

    results = hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_post(url, data, headers, timeout):
        raise hug.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(hug.requests, "post", fake_post)

    assert hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"
        encoding = "utf-8"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(hug.requests, "post", lambda url, data, headers, timeout: FakeResponse())

    assert hug.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_hug.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.hug'`

- [ ] **Step 3: `crawlers/hug.py` 작성**

```python
"""
hana_p — 주택도시보증공사(HUG) 보도자료 스크래퍼. API 키 불필요.
"""

from datetime import date

import requests
from bs4 import BeautifulSoup

_LIST_URL = "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000001.jsp"
_DETAIL_URL = "https://www.khug.or.kr/khmb/m/hs/nd/hsnd000002.jsp"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
# 이 게시판은 페이지 전환이 아니라 "rowSize"만큼 누적해서 더 보여주는 방식이라
# (POST할 때마다 처음부터 rowSize개를 다시 돌려줌), 매번 응답 전체를 다시 받아
# 이전에 처리한 개수 이후의 새 행만 처리한다.
_ROW_STEP = 20
_MAX_ROWS = 500
_NEW_BADGE = "최근 게시물"


def _to_iso_date(raw: str) -> str:
    """'2026.07.27' 형식을 '2026-07-27'로 변환한다."""
    parts = [p for p in raw.strip().split(".") if p]
    if len(parts) != 3:
        return ""
    year, month, day = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """HUG 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만 제공되고
    날짜 범위 조회 파라미터가 없어, rowSize를 늘려가며 새로 나타난 행 중 start보다
    오래된 글을 만나면 멈춘다. 응답은 EUC-KR로 인코딩되어 있다. 네트워크 오류나
    페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가 전체 수집 과정을
    중단시키면 안 된다."""
    try:
        results = []
        prev_count = 0
        row_size = _ROW_STEP
        while row_size <= _MAX_ROWS:
            resp = requests.post(
                _LIST_URL,
                data={"rowSize": row_size, "searchCondition": "01", "searchKeyword": ""},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [tr for tr in soup.select("table.tbl-style02 tr") if tr.select_one("a[href]")]
            if len(rows) <= prev_count:
                break
            new_rows = rows[prev_count:]
            prev_count = len(rows)

            reached_start = False
            for tr in new_rows:
                a = tr.select_one("a[href]")
                tds = tr.find_all("td")
                if a is None or not tds:
                    continue
                announced_at = _to_iso_date(tds[-1].get_text(strip=True))
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                title = a.get_text(strip=True)
                if title.startswith(_NEW_BADGE):
                    title = title[len(_NEW_BADGE):].strip()
                idx = a["href"].split("idx=")[-1]
                results.append({
                    "title": title,
                    "url": f"{_DETAIL_URL}?idx={idx}",
                    "department": "",
                    "announced_at": announced_at,
                    "view_count": 0,
                })
            if reached_start:
                break
            row_size += _ROW_STEP
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_hug.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/hug.py tests/test_crawler_hug.py
git commit -m "feat: add HUG press release crawler"
```

---

### Task 9: `crawlers/sh.py` — SH(서울주택도시공사) 보도자료

**Files:**
- Create: `crawlers/sh.py`
- Create: `tests/test_crawler_sh.py`

**Interfaces:**
- Produces: `sh.fetch_press_releases(start: date, end: date) -> list[dict]`(동일 계약).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_crawler_sh.py`:

```python
from datetime import date

from crawlers import sh

_PAGE1_HTML = """
<table>
<tbody>
<tr>
    <td>1469</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('307210');return false;">
        서울주택도시개발공사 방치된 반지하 주택 공유 창고로 활용</a></td>
    <td>홍보부</td>
    <td class="num">2026-07-20</td>
    <td class="num">223</td>
</tr>
<tr>
    <td>1468</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('307029');return false;">
        서울주택도시개발공사 폭염 대비 건설 현장 안전 점검 실시</a></td>
    <td>홍보부</td>
    <td class="num">2026-07-15</td>
    <td class="num">102</td>
</tr>
</tbody>
</table>
"""

_PAGE2_HTML = """
<table>
<tbody>
<tr>
    <td>1400</td>
    <td class="txtL"><a href="#" onclick="javascript:getDetailView('300000');return false;">
        오래된 보도자료</a></td>
    <td>홍보부</td>
    <td class="num">2026-06-01</td>
    <td class="num">1</td>
</tr>
</tbody>
</table>
"""


def test_fetch_press_releases_parses_title_url_department_date_and_views(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("pages", []).append(params["page"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["page"] == 1 else "<table><tbody></tbody></table>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    results = sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139/list.do"
    assert captured["pages"][0] == 1
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "서울주택도시개발공사 방치된 반지하 주택 공유 창고로 활용"
    assert first["url"] == (
        "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139/view.do?seq=307210&page=1"
    )
    assert first["department"] == "홍보부"
    assert first["announced_at"] == "2026-07-20"
    assert first["view_count"] == 223


def test_fetch_press_releases_stops_paging_once_older_than_start(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["page"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(sh.requests, "get", fake_get)

    results = sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 2
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise sh.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(sh.requests, "get", fake_get)

    assert sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_table_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(sh.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert sh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_crawler_sh.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.sh'`

- [ ] **Step 3: `crawlers/sh.py` 작성**

```python
"""
hana_p — SH(서울주택도시공사) 보도자료 스크래퍼. API 키 불필요.
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

_BASE_URL = "https://www.i-sh.co.kr/main/lay2/program/S1T532C1422/brd/m_139"
_LIST_URL = f"{_BASE_URL}/list.do"
_VIEW_URL = f"{_BASE_URL}/view.do"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_MAX_PAGES = 50
# 목록의 상세보기 링크는 <a onclick="getDetailView('seq')"> 처럼 JS로만 이동한다
# (실제 href는 "#") — seq만 추출해 view.do에 대한 GET URL을 직접 구성한다.
_SEQ_RE = re.compile(r"getDetailView\('(\d+)'\)")


def fetch_press_releases(start: date, end: date) -> list[dict]:
    """SH(서울주택도시공사) 보도자료를 start~end 날짜 범위로 가져온다. 목록이 최신순으로만
    제공되고 날짜 범위 조회 파라미터가 없어, 페이지를 넘기며 start보다 오래된 글을 만나면
    멈춘다. 네트워크 오류나 페이지 구조 변경 시 빈 리스트를 반환한다 — 이 함수의 실패가
    전체 수집 과정을 중단시키면 안 된다."""
    try:
        results = []
        for page in range(1, _MAX_PAGES + 1):
            resp = requests.get(
                _LIST_URL, params={"page": page}, headers=_HEADERS, timeout=_TIMEOUT
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [tr for tr in soup.select("table tr") if tr.select_one("a[onclick*=getDetailView]")]
            if not rows:
                break

            reached_start = False
            for tr in rows:
                title_a = tr.select_one("a[onclick*=getDetailView]")
                tds = tr.find_all("td")
                seq_match = _SEQ_RE.search(title_a.get("onclick", "")) if title_a else None
                if title_a is None or seq_match is None or len(tds) < 5:
                    continue
                announced_at = tds[3].get_text(strip=True)
                if not announced_at:
                    continue
                if announced_at < start.isoformat():
                    reached_start = True
                    break
                if announced_at > end.isoformat():
                    continue
                try:
                    view_count = int(tds[4].get_text(strip=True))
                except ValueError:
                    view_count = 0
                results.append({
                    "title": title_a.get_text(strip=True),
                    "url": f"{_VIEW_URL}?seq={seq_match.group(1)}&page=1",
                    "department": tds[2].get_text(strip=True),
                    "announced_at": announced_at,
                    "view_count": view_count,
                })
            if reached_start:
                break
        return results
    except Exception:
        return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_crawler_sh.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crawlers/sh.py tests/test_crawler_sh.py
git commit -m "feat: add SH press release crawler"
```

---

### Task 10: `collector.py` — 정책 수집 오케스트레이션

**Files:**
- Modify: `collector.py`
- Create: `tests/test_collector.py`

**Interfaces:**
- Consumes: `crawlers.{molit,reb,lh,seoul_opengov,hf,hug,sh}.fetch_press_releases`,
  `db.insert_policy_event`, `db.insert_policy_run_log`(Task 2, 3-9)
- Produces: `collector.collect_molit_press_releases(days=30, trigger="수동", run_id=None) -> dict`,
  `collector.collect_reb_press_releases(...)`, `collector.collect_lh_press_releases(...)`,
  `collector.collect_seoul_opengov_press_releases(...)`, `collector.collect_hf_press_releases(...)`,
  `collector.collect_hug_press_releases(...)`, `collector.collect_sh_press_releases(...)`
  (모두 `{"fetched": int, "inserted": int, "skipped": int}` 반환),
  `collector.collect_all_policy_events(days=30, on_progress=None, trigger="수동", run_id=None) -> dict`,
  `collector.active_policy_run_id() -> str | None`,
  `collector.get_policy_progress(run_id: str) -> list[dict]`,
  `collector.start_background_policy_collection(days=30, trigger="수동") -> str | None` —
  Task 11(scheduler)과 Task 12(UI)가 그대로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_collector.py` 새로 생성 (기존 브랜드 수집용 `test_collector.py`가 없으므로 정책
부분만 다룬다):

```python
import time

import collector
import db


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(collector, "_active_policy_run_id", None)
    monkeypatch.setattr(collector, "_policy_progress", {})


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
            lambda start, end: [_fake_release("https://x/1")],
        )

    result = collector.collect_all_policy_events(days=30)

    assert result["국토부"] == {"fetched": 0, "inserted": 0, "skipped": 0}
    assert result["LH"]["inserted"] == 1


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
            lambda start, end: [_fake_release("https://x/1")],
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_collector.py -v`
Expected: FAIL — `AttributeError: module 'collector' has no attribute 'molit_crawler'`

- [ ] **Step 3: `collector.py`에 정책 수집 로직 추가**

`collector.py` 상단 import 블록에 추가(`from crawlers import daum as daum_crawler` 등 기존
import들 사이, 알파벳 순 유지):

```python
from crawlers import hf as hf_crawler
from crawlers import hug as hug_crawler
from crawlers import lh as lh_crawler
from crawlers import molit as molit_crawler
from crawlers import reb as reb_crawler
from crawlers import seoul_opengov as seoul_opengov_crawler
from crawlers import sh as sh_crawler
```

`from datetime import datetime`를 `from datetime import date, datetime, timedelta`로 교체.

기존 `_state_lock = threading.Lock()` / `_active_run_id: str | None = None` 바로 아래에 추가:

```python
_policy_state_lock = threading.Lock()
_active_policy_run_id: str | None = None
_policy_progress: dict[str, list[dict]] = {}
```

파일 끝(`_collect_one` 함수 뒤)에 추가:

```python
def _collect_press_releases(
    fetch_press_releases, source: str, days: int, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """모든 정책 소스 수집 함수가 공유하는 fetch→source 태깅→저장→이력 기록 로직.
    소스별 fetch_press_releases 자체가 실패 시 빈 리스트를 반환해 이 함수는 예외를
    전파하지 않는다. run_id를 주지 않으면(단일 소스 수동 실행 등) 새로 생성해
    그 자체로 1건짜리 배치가 된다."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    records = fetch_press_releases(start, today)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inserted = 0
    skipped = 0
    for record in records:
        record["source"] = source
        record["collected_at"] = now
        if db.insert_policy_event(record):
            inserted += 1
        else:
            skipped += 1

    result = {"fetched": len(records), "inserted": inserted, "skipped": skipped}
    db.insert_policy_run_log({
        "ran_at": now, "trigger": trigger, "source": source, "run_id": run_id or str(uuid.uuid4())[:8],
        "ok": 1, "message": "", **result,
    })
    return result


def collect_molit_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """국토교통부 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(molit_crawler.fetch_press_releases, "국토부", days, trigger, run_id)


def collect_reb_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """한국부동산원 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(
        reb_crawler.fetch_press_releases, "한국부동산원", days, trigger, run_id
    )


def collect_lh_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """LH 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(lh_crawler.fetch_press_releases, "LH", days, trigger, run_id)


def collect_seoul_opengov_press_releases(
    days: int = 30, trigger: str = "수동", run_id: str | None = None
) -> dict:
    """서울시 정보소통광장 보도자료(주택/도시계획 관련만) 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(
        seoul_opengov_crawler.fetch_press_releases, "서울시", days, trigger, run_id
    )


def collect_hf_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """한국주택금융공사(HF) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(hf_crawler.fetch_press_releases, "HF", days, trigger, run_id)


def collect_hug_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """주택도시보증공사(HUG) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(hug_crawler.fetch_press_releases, "HUG", days, trigger, run_id)


def collect_sh_press_releases(days: int = 30, trigger: str = "수동", run_id: str | None = None) -> dict:
    """SH(서울주택도시공사) 보도자료를 최근 days일치 가져와 저장한다."""
    return _collect_press_releases(sh_crawler.fetch_press_releases, "SH", days, trigger, run_id)


def collect_all_policy_events(
    days: int = 30, on_progress=None, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """국토부/한국부동산원/LH/서울시/HF/HUG/SH 정책 데이터를 순서대로 모두 수집한다.
    소스별 함수가 각자 실패에 안전하므로(예외 대신 빈 리스트/스킵 처리) 한 소스의
    문제가 다른 소스 수집을 막지 않는다. 스케줄러가 자동 실행할 때도 사용한다.
    on_progress가 주어지면 소스 하나가 끝날 때마다 (source, result)로 호출된다.
    7개 소스 모두 같은 run_id로 이력에 기록되어 "수집 이력"에서 1세트로 묶인다."""
    run_id = run_id or str(uuid.uuid4())[:8]
    sources = [
        ("국토부", collect_molit_press_releases),
        ("한국부동산원", collect_reb_press_releases),
        ("LH", collect_lh_press_releases),
        ("서울시", collect_seoul_opengov_press_releases),
        ("HF", collect_hf_press_releases),
        ("HUG", collect_hug_press_releases),
        ("SH", collect_sh_press_releases),
    ]
    results = {}
    for source, collect_fn in sources:
        result = collect_fn(days=days, trigger=trigger, run_id=run_id)
        results[source] = result
        if on_progress is not None:
            on_progress(source, result)
    return results


def active_policy_run_id() -> str | None:
    """start_background_policy_collection()으로 시작된 정책 수집이 아직 진행 중이면
    그 run_id, 아니면 None. 브랜드 수집(active_run_id)과는 독립적으로 추적된다."""
    with _policy_state_lock:
        return _active_policy_run_id


def get_policy_progress(run_id: str) -> list[dict]:
    """start_background_policy_collection()이 진행되며 소스별로 쌓아온 결과 목록을 반환한다."""
    with _policy_state_lock:
        return list(_policy_progress.get(run_id, []))


def start_background_policy_collection(days: int = 30, trigger: str = "수동") -> str | None:
    """이미 진행 중인 백그라운드 정책 수집이 없으면 데몬 스레드로 시작하고 run_id를
    반환한다. 이미 진행 중이면 아무 것도 하지 않고 None을 반환한다(중복 실행 방지).
    이 run_id는 실시간 진행 조회(get_policy_progress)와 "수집 이력"(db.get_policy_run_batches)에
    동일하게 쓰인다."""
    global _active_policy_run_id
    with _policy_state_lock:
        if _active_policy_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_policy_run_id = run_id
        _policy_progress[run_id] = []

    def _on_progress(source, result):
        with _policy_state_lock:
            _policy_progress[run_id].append({"source": source, **result})

    def _worker():
        global _active_policy_run_id
        try:
            collect_all_policy_events(days=days, on_progress=_on_progress, trigger=trigger, run_id=run_id)
        finally:
            with _policy_state_lock:
                _active_policy_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_collector.py -v`
Expected: PASS (16 tests). 배경 스레드를 쓰는 마지막 두 테스트는 타이밍에 민감할 수 있으니
1~2회 재시도해서 안정적으로 통과하는지 확인.

- [ ] **Step 5: Commit**

```bash
git add collector.py tests/test_collector.py
git commit -m "feat: add policy collection orchestration to collector"
```

---

### Task 11: `scheduler.py` — 정책 전용 자동 스케줄

**Files:**
- Modify: `scheduler.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `utils.load_policy_collection_schedule`(Task 1),
  `collector.collect_all_policy_events`(Task 10)
- Produces: `scheduler._tick_policy()`, `scheduler._POLICY_COLLECTION_DAYS = 3`,
  `scheduler._last_fired_policy`(내부 상태, 테스트에서 모킹 대상) — Task 12의 UI 텍스트에서
  참조하지는 않지만 자동 수집이 실제로 동작하는 근거가 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_scheduler.py` 새로 생성(기존 브랜드 스케줄러도 지금까지 테스트가 없었으므로,
이번에 브랜드+정책 양쪽을 함께 커버한다):

```python
from datetime import datetime

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


def test_tick_new_posts_and_policy_fire_on_their_own_independent_schedules(monkeypatch):
    """신규 게시물과 정부 정책은 각자 등록된 시각에만, 서로 무관하게 실행된다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})

    brand_calls = []
    policy_calls = []
    monkeypatch.setattr(scheduler.collector, "run_collection", lambda trigger: brand_calls.append(trigger))
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events",
        lambda days, trigger: policy_calls.append((days, trigger)) or {},
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

    calls = []
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events", lambda days, trigger: calls.append(days) or {}
    )

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_policy_collection(monkeypatch, caplog):
    """collect_all_policy_events()이 예외를 던져도 _tick()은 전파하지 않는다."""
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})

    def boom(days, trigger):
        raise RuntimeError("policy collection failed")

    monkeypatch.setattr(scheduler.collector, "collect_all_policy_events", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_policy == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)


def test_tick_swallows_exception_from_load_policy_collection_schedule(monkeypatch, caplog):
    """load_policy_collection_schedule()이 예외를 던져도 _tick()은 전파하지 않고 로깅한다.
    신규 게시물 체크는 이 예외와 무관하게 독립적으로 동작한다."""
    _reset(monkeypatch)
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})

    def boom():
        raise RuntimeError("policy schedule file corrupted")

    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert any("오류" in record.message for record in caplog.records)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL — `AttributeError: module 'scheduler' has no attribute '_last_fired_policy'`

- [ ] **Step 3: `scheduler.py`를 정책 틱이 포함되도록 재구성**

`scheduler.py` 전체를 다음으로 교체:

```python
"""
hana_p — 등록된 시각에 맞춰 자동 수집을 실행하는 백그라운드 스케줄러.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import collector
from utils import load_collection_schedule, load_policy_collection_schedule

_POLL_SECONDS = 30
# 폴링 주기가 아니라 "혹시 한 번 놓쳐도 다음 실행에서 메꿔지도록" 여유를 둔 값 —
# 정책 게시판은 URL UNIQUE로 어차피 중복 저장되지 않으니 매번 겹치게 가져와도 안전하다.
_POLICY_COLLECTION_DAYS = 3
_last_fired = ""
_last_fired_policy = ""
_lock = threading.Lock()
_started = False

_LOG_DIR = Path(__file__).resolve().parent / "data"
_LOG_FILE = _LOG_DIR / "scheduler.log"

logger = logging.getLogger("hana_p.scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)


def schedule_matches_now(times: list, now: datetime) -> bool:
    return now.strftime("%H:%M") in times


def _tick_new_posts() -> None:
    """신규 게시물(브랜드/시장 키워드) 자동 수집 체크. 예외를 상위로 전파하지 않는다."""
    global _last_fired
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired
        if not already_fired:
            schedules = load_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired = minute_key
                collector.run_collection(trigger="자동")
    except Exception:
        logger.exception("스케줄러(신규 게시물) 반복 실행 중 오류 발생")


def _tick_policy() -> None:
    """정부 정책 자동 수집 체크. 신규 게시물과 독립된 스케줄/예외 처리."""
    global _last_fired_policy
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_policy
        if not already_fired:
            schedules = load_policy_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_policy = minute_key
                result = collector.collect_all_policy_events(days=_POLICY_COLLECTION_DAYS, trigger="자동")
                logger.info("정책 데이터 자동 수집 결과: %s", result)
    except Exception:
        logger.exception("스케줄러(정부 정책) 반복 실행 중 오류 발생")


def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책은 각자 독립된 스케줄로 체크한다."""
    _tick_new_posts()
    _tick_policy()


def _loop() -> None:
    while True:
        _tick()
        time.sleep(_POLL_SECONDS)


def start_scheduler_thread() -> None:
    """앱 프로세스당 1회만 스레드를 시작한다 (Streamlit 재실행에도 중복 방지)."""
    global _started
    if _started:
        return
    _started = True
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: add independent auto-schedule for policy collection"
```

---

### Task 12: `views/settings.py` — "데이터 수집" 탭에 정부 정책 서브탭 추가

**Files:**
- Modify: `views/settings.py:311-430`(기존 `_render_data_collection` 본문),
  `views/settings.py:15-20`(import 블록)

**Interfaces:**
- Consumes: `collector.collect_{molit,reb,lh,seoul_opengov,hf,hug,sh}_press_releases`,
  `collector.collect_all_policy_events`, `collector.active_policy_run_id`,
  `collector.get_policy_progress`, `collector.start_background_policy_collection`(Task 10),
  `db.get_policy_run_batches`(Task 2), `utils.load_policy_collection_schedule`,
  `utils.save_policy_collection_schedule`(Task 1)
- Produces: `render()`가 호출하는 `_render_data_collection()`은 그대로 유지되지만 내부적으로
  "📰 신규 게시물"/"🏛️ 정부 정책" 서브탭으로 나뉜다 — 시그니처·호출부(`render()`)는 변경 없음.

- [ ] **Step 1: import 블록 갱신**

`views/settings.py`의 기존 import:

```python
from utils import (
    load_collection_schedule,
    load_keywords,
    save_collection_schedule,
    save_keywords,
)
```

를 다음으로 교체:

```python
from utils import (
    load_collection_schedule,
    load_keywords,
    load_policy_collection_schedule,
    save_collection_schedule,
    save_keywords,
    save_policy_collection_schedule,
)
```

- [ ] **Step 2: 기존 `_render_data_collection` 함수를 `_render_brand_collection_tab`으로 이름만 변경**

`views/settings.py:311`의 `def _render_data_collection():`를
`def _render_brand_collection_tab():`로 이름만 바꾸고, 함수 본문(311~430줄)은 그대로 둔다.

- [ ] **Step 3: 정책 수집 탭 렌더 함수 추가**

이름이 바뀐 `_render_brand_collection_tab` 함수 바로 뒤(기존 430번째 줄 이후, "데이터 관리(조회)"
섹션 주석 이전)에 추가:

```python
_POLICY_SOURCE_SECTIONS = [
    ("policy_collect_now", "🏛️ 국토교통부 보도자료", "국토교통부 보도자료를 수집합니다.",
     collector.collect_molit_press_releases),
    ("policy_reb_collect_now", "🏢 한국부동산원 보도자료", "한국부동산원 보도자료(가격동향 등)를 수집합니다.",
     collector.collect_reb_press_releases),
    ("policy_lh_collect_now", "🏗️ LH(한국토지주택공사) 보도자료", "LH 보도자료(공급·보상·사업 진행 등)를 수집합니다.",
     collector.collect_lh_press_releases),
    ("policy_seoul_collect_now", "🏙️ 서울시 정보소통광장 보도자료", "서울시 보도자료 중 주택/도시계획 관련만 수집합니다.",
     collector.collect_seoul_opengov_press_releases),
    ("policy_hf_collect_now", "🏦 HF(한국주택금융공사) 보도자료", "HF 보도자료(주택담보대출·보금자리론 등)를 수집합니다.",
     collector.collect_hf_press_releases),
    ("policy_hug_collect_now", "🛡️ HUG(주택도시보증공사) 보도자료", "HUG 보도자료(전세보증·분양보증 등)를 수집합니다.",
     collector.collect_hug_press_releases),
    ("policy_sh_collect_now", "🏘️ SH(서울주택도시공사) 보도자료", "SH 보도자료(공공주택 공급·정비사업 등)를 수집합니다.",
     collector.collect_sh_press_releases),
]

_POLICY_SOURCE_COUNT = 7


@st.fragment(run_every=2)
def _show_policy_collection_progress(run_id):
    entries = collector.get_policy_progress(run_id)
    if entries:
        st.dataframe(
            pd.DataFrame([
                {"수집처": e["source"], "조회": e["fetched"], "신규": e["inserted"], "중복": e["skipped"]}
                for e in entries
            ]),
            use_container_width=True, hide_index=True,
        )
    if collector.active_policy_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(entries)}/{_POLICY_SOURCE_COUNT}곳 완료)")
    else:
        total_fetched = sum(e["fetched"] for e in entries)
        total_inserted = sum(e["inserted"] for e in entries)
        st.success(f"전체 완료 — {total_fetched}건 조회, 신규 {total_inserted}건")


def _render_policy_collection_tab():
    st.caption(
        "국토교통부·한국부동산원·LH·서울시·HF·HUG·SH 7곳 보도자료를 수집합니다. "
        "신규 게시물과 별도의 독립된 스케줄을 가집니다."
    )
    st.subheader("⏰ 수집 스케줄")
    policy_sched_cfg = load_policy_collection_schedule()
    policy_times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(policy_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="policy_sched_times_text",
    )
    if st.button("💾 저장", key="policy_sched_save"):
        tokens = [t.strip() for t in policy_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_policy_collection_schedule({"times": seen})
            st.rerun()
    if policy_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(policy_sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")

    st.divider()

    running_policy_run_id = collector.active_policy_run_id()
    if running_policy_run_id is None:
        if st.button("🔄 7곳 전체 지금 수집", key="policy_collect_all_now", type="primary"):
            started_run_id = collector.start_background_policy_collection(days=30)
            if started_run_id:
                st.session_state["watched_policy_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 정책 수집이 진행 중입니다.")
    else:
        st.info("🔄 정책 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_policy_run_id"] = running_policy_run_id

    display_policy_run_id = running_policy_run_id or st.session_state.get("watched_policy_run_id")
    if display_policy_run_id:
        _show_policy_collection_progress(display_policy_run_id)

    with st.expander("소스별로 하나씩 수집하기"):
        for i, (key, title, caption, collect_fn) in enumerate(_POLICY_SOURCE_SECTIONS):
            st.markdown(f"#### {title}")
            st.caption(caption)
            if st.button("🔄 지금 수집", key=key):
                result = collect_fn(days=30)
                st.success(
                    f"{result['fetched']}건 조회 (신규 {result['inserted']}, "
                    f"중복 {result['skipped']})"
                )
            if i < len(_POLICY_SOURCE_SECTIONS) - 1:
                st.divider()

    st.divider()
    st.subheader("📜 수집 이력")
    policy_batches = db.get_policy_run_batches(limit=50)
    if policy_batches:
        policy_batch_df = pd.DataFrame(policy_batches)[
            ["ran_at", "trigger", "sources", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(policy_batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")


def _render_data_collection():
    tab_existing, tab_policy = st.tabs(["📰 신규 게시물", "🏛️ 정부 정책"])
    with tab_existing:
        _render_brand_collection_tab()
    with tab_policy:
        _render_policy_collection_tab()
```

- [ ] **Step 4: 수동 검증**

Run: `streamlit run app.py`

1. 관리자 IP로 접속해 "설정 → 🔄 데이터 수집" 탭 진입
2. "📰 신규 게시물" 서브탭이 기존과 동일하게 동작하는지 확인(회귀 없음)
3. "🏛️ 정부 정책" 서브탭에서 시각 입력 후 저장 → `data/policy_collection_schedule.json` 생성
   확인
4. "소스별로 하나씩 수집하기"를 펼쳐 국토교통부 항목만 "🔄 지금 수집" 클릭 → 요약 메시지
   표시 확인
5. "🔄 7곳 전체 지금 수집" 클릭 → 진행 표 갱신 후 "전체 완료" 메시지, "📜 수집 이력"에 배치
   1건 표시 확인

Expected: 위 5단계 모두 오류 없이 동작.

- [ ] **Step 5: Commit**

```bash
git add views/settings.py
git commit -m "feat: add policy collection sub-tab to data collection settings page"
```

---

### Task 13: `views/settings.py` — "데이터 관리" 탭에 정부 정책 서브탭 추가

**Files:**
- Modify: `views/settings.py:463-612`(기존 `_render_data_management` 본문)

**Interfaces:**
- Consumes: `db.get_policy_events`, `db.delete_policy_events`, `db.delete_all_policy_events`
  (Task 2)
- Produces: `render()`가 호출하는 `_render_data_management()`는 그대로 유지되지만 내부적으로
  "📰 신규 게시물"/"🏛️ 정부 정책" 서브탭으로 나뉜다.

- [ ] **Step 1: 기존 `_render_data_management` 함수를 `_render_brand_lookup_tab`으로 이름만 변경**

`views/settings.py:463`의 `def _render_data_management():`를
`def _render_brand_lookup_tab():`로 이름만 바꾸고, 함수 본문(463~612줄)은 그대로 둔다.

- [ ] **Step 2: 정책 조회 탭 렌더 함수 추가**

이름이 바뀐 `_render_brand_lookup_tab` 함수 바로 뒤에 추가:

```python
_POLICY_ROW_COL_RATIOS = [0.3, 0.8, 1.0, 1.0, 4.0, 0.8, 0.6]
_POLICY_ROW_HEADERS = ["수집처", "등록일", "분류", "제목", "조회수", ""]


@st.dialog("정책 상세 정보", width="large")
def _show_policy_event_detail(row):
    st.subheader(row["제목"])
    st.write(
        f"수집처: {row['수집처']}  |  분류: {row['분류']}  |  "
        f"등록일: {row['등록일']}  |  조회수: {row['조회수']}"
    )
    st.markdown(f"[원문 링크]({row['URL']})")


def _render_policy_lookup_tab():
    """정부 정책 탭 전용 필터+표+삭제 UI. policy_events는 브랜드/채널/게시일 개념이
    없어 _render_brand_lookup_tab과 컬럼 구성이 다르다(등록일/분류/제목/조회수)."""
    departments = ["전체"] + sorted({e["department"] for e in db.get_policy_events() if e["department"]})
    selected_department = st.selectbox("분류", departments, key="policy_lookup_department")
    title_search = st.text_input("제목 검색", placeholder="검색어 입력...", key="policy_lookup_title_search")

    default_range_start = date.today() - timedelta(days=29)
    default_range_end = date.today()
    col_date_filter, col_date_start, col_date_end = st.columns(3)
    with col_date_filter:
        filter_by_date = st.checkbox("등록일로 필터링", key="policy_lookup_filter_by_date")
    with col_date_start:
        date_start = st.date_input(
            "등록일 시작", value=default_range_start,
            key="policy_lookup_date_start", disabled=not filter_by_date,
        )
    with col_date_end:
        date_end = st.date_input(
            "등록일 종료", value=default_range_end,
            key="policy_lookup_date_end", disabled=not filter_by_date,
        )

    events = db.get_policy_events(
        department="" if selected_department == "전체" else selected_department,
    )
    df = pd.DataFrame(
        events,
        columns=["id", "source", "title", "url", "department", "announced_at", "view_count"],
    ).rename(columns={
        "source": "수집처", "title": "제목", "url": "URL", "department": "분류",
        "announced_at": "등록일", "view_count": "조회수",
    })

    if title_search:
        df = df[df["제목"].str.contains(title_search, case=False, na=False)]
    if filter_by_date:
        df = df[
            (df["등록일"] >= date_start.isoformat())
            & (df["등록일"] <= date_end.isoformat())
        ]

    total = len(df)
    st.markdown(f"#### 조회 결과 ({total}건)")

    if df.empty:
        st.caption("조회된 데이터가 없습니다.")
    else:
        header_cols = st.columns([0.5] + _POLICY_ROW_COL_RATIOS[1:])
        for label, col in zip(_POLICY_ROW_HEADERS, header_cols[1:]):
            col.markdown(f"**{label}**")

        for _, row in df.iterrows():
            row_id = int(row["id"])
            cols = st.columns([0.5] + _POLICY_ROW_COL_RATIOS[1:])
            cols[0].checkbox("", key=f"policy_lookup_row_select_{row_id}", label_visibility="collapsed")
            cols[1].markdown(str(row["수집처"]))
            cols[2].markdown(str(row["등록일"]))
            cols[3].markdown(str(row["분류"]))
            title_text = str(row["제목"]).replace("<", "&lt;").replace(">", "&gt;")
            cols[4].markdown(
                f'<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
                f'title="{title_text}">{title_text}</div>',
                unsafe_allow_html=True,
            )
            cols[5].markdown(str(row["조회수"]))
            if cols[6].button("보기", key=f"policy_lookup_view_{row_id}", use_container_width=True):
                _show_policy_event_detail(row)

    selected_ids = [
        int(row["id"]) for _, row in df.iterrows()
        if st.session_state.get(f"policy_lookup_row_select_{int(row['id'])}", False)
    ]

    del_col, count_col = st.columns([1, 5])
    if del_col.button("🗑 선택 삭제", key="policy_lookup_delete_button", disabled=not selected_ids):
        deleted = db.delete_policy_events(selected_ids)
        st.success(f"{deleted}건 삭제했습니다.")
        st.rerun()
    count_col.caption(f"선택된 항목: {len(selected_ids)}건")

    delete_all_confirm = st.checkbox(
        "⚠️ 전체 삭제에 동의합니다 (필터와 무관하게 모든 정책 데이터가 삭제됩니다)",
        key="policy_lookup_delete_all_confirm",
    )
    if st.button(
        "🗑️ 전체 삭제", key="policy_lookup_delete_all_button", disabled=not delete_all_confirm,
    ):
        deleted = db.delete_all_policy_events()
        st.success(f"전체 {deleted}건을 삭제했습니다.")
        st.rerun()


def _render_data_management():
    tab_existing, tab_policy = st.tabs(["📰 신규 게시물", "🏛️ 정부 정책"])
    with tab_existing:
        _render_brand_lookup_tab()
    with tab_policy:
        _render_policy_lookup_tab()
```

- [ ] **Step 3: 수동 검증**

Run: `streamlit run app.py`(이미 실행 중이면 재사용)

1. "설정 → 🗃 데이터 관리" 탭에서 "📰 신규 게시물" 서브탭이 기존과 동일하게 동작하는지 확인
2. "🏛️ 정부 정책" 서브탭에서 Task 12의 5단계에서 수집한 데이터가 조회되는지 확인
3. 분류 선택박스로 필터링, 제목 검색, 등록일 필터 각각 동작 확인
4. "보기" 클릭 → 상세 팝업에 수집처/분류/등록일/조회수/원문 링크 표시 확인
5. 항목 1개 선택 후 "🗑 선택 삭제" → 삭제 확인, 이어서 "📰 신규 게시물" 탭으로 돌아가
   브랜드 데이터가 그대로 남아있는지 확인(정책 삭제가 mentions에 영향 없음)

Expected: 위 5단계 모두 오류 없이 동작, 특히 5번에서 브랜드 데이터 건수가 변하지 않아야 함.

- [ ] **Step 4: Commit**

```bash
git add views/settings.py
git commit -m "feat: add policy lookup sub-tab to data management settings page"
```

---

## Self-Review 결과

**Spec coverage:** 설계 문서의 5개 구현 범위(db.py, crawlers/, collector.py,
utils.py/scheduler.py, views/settings.py) 모두 Task 2·3-9·10·1+11·12-13에 매핑됨.
자동 스케줄 기본값(09~17시 매시)은 UI에서 사용자가 직접 입력해야 적용되므로(Task 1/12는
빈 기본값에서 시작), 최초 배포 시 관리자가 한 번 등록해야 함 — Task 12 Step 4 수동 검증에
포함됨.

**Placeholder scan:** 없음 — 모든 스텝에 실제 코드/명령 포함.

**Type consistency:** `collect_*_press_releases(days, trigger, run_id)` 시그니처가
Task 10(정의)/Task 11(스케줄러 호출은 `days`만 키워드로 사용)/Task 12(UI는 `days=30`만
사용) 전체에서 일관됨. `db.get_policy_events`/`insert_policy_event`/`delete_policy_events`
필드명(`source, title, url, department, announced_at, view_count, collected_at`)이
Task 2(정의)·10(저장)·13(조회 UI 컬럼 매핑) 전체에서 동일함.
