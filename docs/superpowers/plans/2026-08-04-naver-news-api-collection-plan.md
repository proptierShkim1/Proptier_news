# 네이버뉴스 API 수집 채널 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 공식 뉴스 검색 API를 "신규 게시물"(네이버/구글/다음/커뮤니티)·"정부 정책"과
완전히 독립된 3번째 수집 탭으로 추가한다.

**Architecture:** 새 크롤러 모듈(`crawlers/naver_news_api.py`)이 네이버 공식 API를
호출해 기존 4채널 크롤러와 동일한 레코드 형태를 반환한다. `collector.py`는 기존
`_collect_one` 헬퍼를 재사용해 브랜드별로 이 크롤러를 호출하는 독립된 실행/락 상태
(`run_naver_news_collection` / `start_background_naver_news_collection` /
`active_naver_news_run_id`)를 갖는다. 저장은 기존 `mentions`/`run_logs` 테이블을
그대로 재사용하며 `channel="네이버뉴스"`로만 구분한다. 스케줄(`scheduler.py`)과
UI(`views/settings.py`)도 신규 게시물/정부 정책과 나란히 독립적으로 추가한다.

**Tech Stack:** Python, Streamlit, SQLite(`sqlite3`), `requests`, `pytest` + `monkeypatch`.

## Global Constraints

- 채널명은 반드시 `"네이버뉴스"`로 고정한다 (기존 스크래핑 채널 `"네이버"`와 절대
  혼동되지 않아야 함 — `mentions.channel`/`run_logs.channel` 값으로 구분).
- 본문(전문) 스크래핑은 하지 않는다 — API가 주는 `description`만 `snippet`에 저장,
  `content`는 항상 빈 문자열.
- `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`은 `.env`에서만 읽는다 (UI 입력 폼 없음,
  코드에도 하드코딩하지 않음). 크롤러 함수는 이 값을 **호출 시점에** `os.getenv`로
  읽어야 한다(모듈 임포트 시점에 읽으면 `load_dotenv()` 호출 순서에 따라 빈 값을 캐싱할
  수 있음).
- 기존 `mentions`/`run_logs` 테이블 스키마는 변경하지 않는다 — 신규 테이블 없음.
- 키워드는 별도로 관리하지 않고 기존 "키워드 관리"(`load_keywords()`)의 보유·경쟁사·
  시장 키워드를 그대로 검색어로 사용한다.

---

### Task 1: `crawlers/naver_news_api.py` — 네이버 뉴스 검색 API 크롤러

**Files:**
- Create: `crawlers/naver_news_api.py`
- Test: `tests/test_crawler_naver_news_api.py`

**Interfaces:**
- Produces: `search(term: str) -> list[dict]` — 각 항목은
  `{"source_detail": "뉴스", "title": str, "url": str, "snippet": str, "posted_at": str}`.
  자격증명이 없으면 `RuntimeError`, API 호출 실패 시 `requests.exceptions.RequestException`
  계열 예외가 그대로 전파된다(다른 크롤러와 달리 이 모듈은 예외를 삼키지 않음 —
  상위 `collector._collect_one`이 이미 term 단위로 try/except 처리한다).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_crawler_naver_news_api.py
import pytest

from crawlers import naver_news_api


def _set_credentials(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_parses_and_strips_bold_tags_and_prefers_originallink(monkeypatch):
    _set_credentials(monkeypatch)
    payload = {
        "items": [
            {
                "title": "<b>프롭티어</b> 전세사기 예방 서비스 출시",
                "originallink": "https://example.com/news/1",
                "link": "https://news.naver.com/1",
                "description": "<b>프롭티어</b>가 전세사기 예방 서비스를 출시했다.",
                "pubDate": "Mon, 03 Aug 2026 09:00:00 +0900",
            }
        ]
    }
    monkeypatch.setattr(
        naver_news_api.requests, "get",
        lambda url, params, headers, timeout: _FakeResponse(payload),
    )

    results = naver_news_api.search("프롭티어")

    assert results == [{
        "source_detail": "뉴스",
        "title": "프롭티어 전세사기 예방 서비스 출시",
        "url": "https://example.com/news/1",
        "snippet": "프롭티어가 전세사기 예방 서비스를 출시했다.",
        "posted_at": "2026.08.03",
    }]


def test_search_falls_back_to_link_when_originallink_missing(monkeypatch):
    _set_credentials(monkeypatch)
    payload = {"items": [{
        "title": "제목", "link": "https://news.naver.com/1",
        "description": "요약", "pubDate": "Mon, 03 Aug 2026 09:00:00 +0900",
    }]}
    monkeypatch.setattr(
        naver_news_api.requests, "get",
        lambda url, params, headers, timeout: _FakeResponse(payload),
    )

    results = naver_news_api.search("프롭티어")

    assert results[0]["url"] == "https://news.naver.com/1"


def test_search_sends_client_credentials_and_query_in_request(monkeypatch):
    _set_credentials(monkeypatch)
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _FakeResponse({"items": []})

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    naver_news_api.search("프롭티어")

    assert captured["url"] == "https://openapi.naver.com/v1/search/news.json"
    assert captured["headers"]["X-Naver-Client-Id"] == "test-id"
    assert captured["headers"]["X-Naver-Client-Secret"] == "test-secret"
    assert captured["params"]["query"] == "프롭티어"


def test_search_raises_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    with pytest.raises(RuntimeError):
        naver_news_api.search("프롭티어")


def test_search_propagates_request_exception(monkeypatch):
    _set_credentials(monkeypatch)

    def fake_get(url, params, headers, timeout):
        raise naver_news_api.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(naver_news_api.requests, "get", fake_get)

    with pytest.raises(naver_news_api.requests.exceptions.RequestException):
        naver_news_api.search("프롭티어")
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_crawler_naver_news_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crawlers.naver_news_api'`

- [ ] **Step 3: 최소 구현 작성**

```python
# crawlers/naver_news_api.py
"""
hana_p — 네이버 공식 뉴스 검색 API 클라이언트. Client ID/Secret 필요(.env:
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET).
"""

import os
import re
from email.utils import parsedate_to_datetime

import requests

_API_URL = "https://openapi.naver.com/v1/search/news.json"
_TIMEOUT = 10
_DISPLAY = 100

_BOLD_TAG_RE = re.compile(r"</?b>")


def _clean(text: str) -> str:
    return _BOLD_TAG_RE.sub("", text).strip()


def _auth_headers() -> dict:
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "NAVER_CLIENT_ID/NAVER_CLIENT_SECRET이 설정되지 않았습니다 (.env 확인)."
        )
    return {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}


def _format_posted_at(pub_date: str) -> str:
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y.%m.%d")
    except (TypeError, ValueError):
        return ""


def search(term: str) -> list[dict]:
    resp = requests.get(
        _API_URL,
        params={"query": term, "display": _DISPLAY, "sort": "date"},
        headers=_auth_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()

    results = []
    for item in payload.get("items", []):
        url = item.get("originallink") or item.get("link", "")
        title = _clean(item.get("title", ""))
        if not url or not title:
            continue
        results.append({
            "source_detail": "뉴스",
            "title": title,
            "url": url,
            "snippet": _clean(item.get("description", "")),
            "posted_at": _format_posted_at(item.get("pubDate", "")),
        })
    return results
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_crawler_naver_news_api.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add crawlers/naver_news_api.py tests/test_crawler_naver_news_api.py
git commit -m "feat: add Naver News API crawler"
```

---

### Task 2: `db.py` — `get_run_batches`에 채널 필터 추가

**Files:**
- Modify: `db.py:161` (`get_run_batches` 함수)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: 없음(기존 `run_logs` 테이블 그대로 사용)
- Produces: `get_run_batches(limit: int = 50, channels: list[str] | None = None) -> list[dict]`
  — `channels`를 주면 그 채널들만 포함된 `run_logs` 행을 대상으로 배치를 묶는다.
  `channels=None`(기본값)이면 기존과 동일하게 전체 채널을 묶는다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_db.py 에 추가

def _run_log_entry(brand="프롭티어", channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"):
    return {
        "ran_at": ran_at, "trigger": "수동", "brand": brand, "channel": channel,
        "fetched": 1, "inserted": 1, "skipped": 0, "ok": 1, "message": "", "run_id": run_id,
    }


def test_get_run_batches_without_channels_filter_returns_everything(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_run_log(_run_log_entry(channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"))
    db.insert_run_log(_run_log_entry(channel="네이버뉴스", run_id="batch2", ran_at="2026-08-04 10:00:00"))

    batches = db.get_run_batches()

    assert len(batches) == 2


def test_get_run_batches_channels_filter_only_includes_matching_channels(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    db.insert_run_log(_run_log_entry(channel="네이버", run_id="batch1", ran_at="2026-08-04 09:00:00"))
    db.insert_run_log(_run_log_entry(channel="네이버뉴스", run_id="batch2", ran_at="2026-08-04 10:00:00"))

    brand_batches = db.get_run_batches(channels=["네이버", "구글", "다음", "커뮤니티"])
    naver_news_batches = db.get_run_batches(channels=["네이버뉴스"])

    assert len(brand_batches) == 1
    assert brand_batches[0]["channels"] == "네이버"
    assert len(naver_news_batches) == 1
    assert naver_news_batches[0]["channels"] == "네이버뉴스"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_db.py -k get_run_batches -v`
Expected: FAIL — `TypeError: get_run_batches() got an unexpected keyword argument 'channels'`

- [ ] **Step 3: 구현 수정**

`db.py`의 기존 `get_run_batches` 함수를 다음으로 교체:

```python
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

    with sqlite3.connect(DB_PATH) as con:
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
```

(로컬 변수명을 `channels` → `run_channels`로 바꾼 것은 함수 파라미터 `channels`와의
섀도잉을 피하기 위함. 반환 딕셔너리의 키 이름 `"channels"`는 그대로 유지.)

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_db.py -v`
Expected: PASS (모든 기존 테스트 포함 전체 통과)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add channel filter to get_run_batches"
```

---

### Task 3: `utils.py` — 네이버뉴스 전용 자동 수집 스케줄

**Files:**
- Modify: `utils.py`
- Test: `tests/test_utils.py`

**Interfaces:**
- Produces: `NAVER_NEWS_COLLECTION_SCHEDULE_FILE: Path`,
  `load_naver_news_collection_schedule() -> dict`,
  `save_naver_news_collection_schedule(cfg: dict) -> None`
  (기존 `load_collection_schedule`/`load_policy_collection_schedule`과 동일한 계약:
  `{"times": [...]}`).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_utils.py — 상단 import를 아래로 교체
from utils import (
    load_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    resolve_relative_korean_date,
    save_collection_schedule,
    save_naver_news_collection_schedule,
    save_policy_collection_schedule,
)
import utils


# 파일 끝에 추가
def test_load_naver_news_collection_schedule_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE",
        tmp_path / "naver_news_collection_schedule.json",
    )

    assert load_naver_news_collection_schedule() == {"times": []}


def test_save_naver_news_collection_schedule_persists_times(tmp_path, monkeypatch):
    schedule_file = tmp_path / "naver_news_collection_schedule.json"
    monkeypatch.setattr(utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE", schedule_file)

    save_naver_news_collection_schedule({"times": ["11:00"]})

    assert json.loads(schedule_file.read_text(encoding="utf-8")) == {"times": ["11:00"]}


def test_naver_news_collection_schedule_is_independent_of_other_schedules(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "COLLECTION_SCHEDULE_FILE", tmp_path / "collection_schedule.json")
    monkeypatch.setattr(
        utils, "POLICY_COLLECTION_SCHEDULE_FILE", tmp_path / "policy_collection_schedule.json"
    )
    monkeypatch.setattr(
        utils, "NAVER_NEWS_COLLECTION_SCHEDULE_FILE", tmp_path / "naver_news_collection_schedule.json"
    )

    save_collection_schedule({"times": ["09:00"]})
    save_policy_collection_schedule({"times": ["10:00"]})
    save_naver_news_collection_schedule({"times": ["11:00"]})

    assert load_collection_schedule() == {"times": ["09:00"]}
    assert load_policy_collection_schedule() == {"times": ["10:00"]}
    assert load_naver_news_collection_schedule() == {"times": ["11:00"]}
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_utils.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_naver_news_collection_schedule'`

- [ ] **Step 3: 구현 작성**

`utils.py`의 `POLICY_COLLECTION_SCHEDULE_FILE` 상수 및
`load_policy_collection_schedule`/`save_policy_collection_schedule` 정의 바로 아래에 추가:

```python
NAVER_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR / "naver_news_collection_schedule.json"


def load_naver_news_collection_schedule() -> dict:
    cfg = load_json(NAVER_NEWS_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_naver_news_collection_schedule(cfg: dict) -> None:
    save_json(NAVER_NEWS_COLLECTION_SCHEDULE_FILE, cfg)
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_utils.py -v`
Expected: PASS (전체 통과)

- [ ] **Step 5: 커밋**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat: add independent schedule config for Naver News API collection"
```

---

### Task 4: `collector.py` — 네이버뉴스 독립 수집 오케스트레이션

**Files:**
- Modify: `collector.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Consumes: `crawlers.naver_news_api.search(term: str) -> list[dict]` (Task 1),
  `_collect_one(brand_entry, channel, crawl, trigger, run_id, context_words, exclude_terms) -> dict`
  (기존 함수, 그대로 재사용), `load_keywords() -> dict` (기존).
- Produces: `run_naver_news_collection(trigger="수동", on_progress=None, run_id=None) -> list[dict]`,
  `start_background_naver_news_collection(trigger="수동") -> str | None`,
  `active_naver_news_run_id() -> str | None`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_collector.py — 상단 _isolate를 아래로 교체
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(collector, "_active_policy_run_id", None)
    monkeypatch.setattr(collector, "_policy_progress", {})
    monkeypatch.setattr(collector, "_active_naver_news_run_id", None)


# 파일 끝에 추가
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_collector.py -k naver_news -v`
Expected: FAIL — `AttributeError: module 'collector' has no attribute 'run_naver_news_collection'`

- [ ] **Step 3: 구현 작성**

`collector.py` 상단 import 블록의 `from crawlers import naver as naver_crawler` 바로
아래 줄에 추가:

```python
from crawlers import naver_news_api as naver_news_api_crawler
```

`_collect_one` 함수(현재 파일의 `def _collect_one(...)` ~ `return entry`) **바로 뒤**,
`def _collect_press_releases(...)` **바로 앞**에 아래 블록을 새로 추가:

```python
_NAVER_NEWS_CHANNEL = "네이버뉴스"

_naver_news_state_lock = threading.Lock()
_active_naver_news_run_id: str | None = None


def active_naver_news_run_id() -> str | None:
    """신규 게시물(active_run_id)·정책(active_policy_run_id)과 독립된 네이버뉴스 API
    수집 실행 상태를 추적한다."""
    with _naver_news_state_lock:
        return _active_naver_news_run_id


def start_background_naver_news_collection(trigger: str = "수동") -> str | None:
    """이미 진행 중인 네이버뉴스 API 수집이 없으면 데몬 스레드로 시작하고 run_id를
    반환한다. 신규 게시물/정책 수집과는 독립된 락이므로 서로 동시에 실행될 수 있다."""
    global _active_naver_news_run_id
    with _naver_news_state_lock:
        if _active_naver_news_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_naver_news_run_id = run_id

    def _worker():
        global _active_naver_news_run_id
        try:
            run_naver_news_collection(trigger=trigger, run_id=run_id)
        finally:
            with _naver_news_state_lock:
                _active_naver_news_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id


def run_naver_news_collection(
    trigger: str = "수동", on_progress=None, run_id: str | None = None
) -> list[dict]:
    """등록된 모든 브랜드 키워드로 네이버뉴스 API를 수집한다. 신규 게시물(4채널)과
    독립된 run_id/이력을 갖되, 노이즈/문맥/제외 필터링과 저장 스키마(_collect_one,
    mentions/run_logs)는 그대로 재사용한다."""
    cfg = load_keywords()
    context_words = cfg.get("context") or []
    exclude_terms = cfg.get("exclude") or []
    run_id = run_id or str(uuid.uuid4())[:8]
    log_entries = []
    for brand_entry in cfg["brands"]:
        entry = _collect_one(
            brand_entry, _NAVER_NEWS_CHANNEL, naver_news_api_crawler.search,
            trigger, run_id, context_words, exclude_terms,
        )
        log_entries.append(entry)
        if on_progress is not None:
            on_progress(entry)
        time.sleep(_REQUEST_DELAY_SECONDS)
    return log_entries
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_collector.py -v`
Expected: PASS (전체 통과)

- [ ] **Step 5: 커밋**

```bash
git add collector.py tests/test_collector.py
git commit -m "feat: add independent Naver News API collection orchestration"
```

---

### Task 5: `scheduler.py` — 네이버뉴스 전용 자동 스케줄 틱

**Files:**
- Modify: `scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `utils.load_naver_news_collection_schedule() -> dict` (Task 3),
  `collector.run_naver_news_collection(trigger: str) -> list[dict]` (Task 4).
- Produces: `_tick_naver_news() -> None`, 모듈 전역 `_last_fired_naver_news: str`.
  `_tick()`이 `_tick_new_posts()`/`_tick_policy()`/`_tick_naver_news()`를 모두 호출.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_scheduler.py — 기존 _reset을 아래로 교체
def _reset(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_fired", "")
    monkeypatch.setattr(scheduler, "_last_fired_policy", "")
    monkeypatch.setattr(scheduler, "_last_fired_naver_news", "")
```

기존 4개 테스트(`test_tick_new_posts_and_policy_fire_on_their_own_independent_schedules`,
`test_tick_policy_does_not_fire_twice_for_same_minute`,
`test_tick_swallows_exception_from_policy_collection`,
`test_tick_swallows_exception_from_load_policy_collection_schedule`) 각각에서
`monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": ["09:00"]})`
(또는 `{"times": []}`) 줄 **바로 다음 줄**에 아래 한 줄을 추가한다(네이버뉴스 틱이 실제
파일시스템의 스케줄 파일을 읽지 않도록 격리):

```python
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
```

파일 끝에 아래 3개 테스트를 새로 추가:

```python
def test_tick_naver_news_fires_on_its_own_independent_schedule(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(scheduler.collector, "run_collection", lambda trigger: calls.append(("brand", trigger)))
    monkeypatch.setattr(
        scheduler.collector, "collect_all_policy_events",
        lambda days, trigger: calls.append(("policy", trigger)) or {},
    )
    monkeypatch.setattr(
        scheduler.collector, "run_naver_news_collection",
        lambda trigger: calls.append(("naver_news", trigger)),
    )

    scheduler._tick()

    assert calls == [("naver_news", "자동")]
    assert scheduler._last_fired_naver_news == "2026-07-16 09:00"


def test_tick_naver_news_does_not_fire_twice_for_same_minute(monkeypatch):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    calls = []
    monkeypatch.setattr(scheduler.collector, "run_naver_news_collection", lambda trigger: calls.append(trigger))

    scheduler._tick()
    scheduler._tick()

    assert len(calls) == 1


def test_tick_swallows_exception_from_naver_news_collection(monkeypatch, caplog):
    _reset(monkeypatch)
    _fix_now(monkeypatch, datetime(2026, 7, 16, 9, 0))
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": ["09:00"]})

    def boom(trigger):
        raise RuntimeError("naver news collection failed")

    monkeypatch.setattr(scheduler.collector, "run_naver_news_collection", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick()

    assert scheduler._last_fired_naver_news == "2026-07-16 09:00"
    assert any("오류" in record.message for record in caplog.records)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL — `AttributeError: module 'scheduler' has no attribute '_last_fired_naver_news'`

- [ ] **Step 3: 구현 작성**

`scheduler.py`의 import 줄을 교체:

```python
from utils import (
    load_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
)
```

`_last_fired_policy = ""` 바로 아래에 추가:

```python
_last_fired_naver_news = ""
```

`_tick_policy()` 함수 정의 바로 뒤, `_tick()` 함수 정의 바로 앞에 추가:

```python
def _tick_naver_news() -> None:
    """네이버뉴스 API 자동 수집 체크. 신규 게시물/정부 정책과 독립된 스케줄/예외 처리."""
    global _last_fired_naver_news
    try:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        with _lock:
            already_fired = minute_key == _last_fired_naver_news
        if not already_fired:
            schedules = load_naver_news_collection_schedule()["times"]
            if schedule_matches_now(schedules, now):
                with _lock:
                    _last_fired_naver_news = minute_key
                collector.run_naver_news_collection(trigger="자동")
    except Exception:
        logger.exception("스케줄러(네이버뉴스 API) 반복 실행 중 오류 발생")
```

`_tick()` 함수 본문을 교체:

```python
def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API는 각자
    독립된 스케줄로 체크한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS (전체 통과)

- [ ] **Step 5: 커밋**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: add independent auto-schedule tick for Naver News API collection"
```

---

### Task 6: `views/settings.py` — 네이버뉴스 API 수집 탭 UI

**Files:**
- Modify: `views/settings.py`

**Interfaces:**
- Consumes: 전부 Task 1~5에서 만든 것 — `collector.run_naver_news_collection`,
  `collector.start_background_naver_news_collection`,
  `collector.active_naver_news_run_id`, `utils.load_naver_news_collection_schedule`,
  `utils.save_naver_news_collection_schedule`, `db.get_run_batches(channels=...)`,
  기존 `_format_entry_status`, `_TIME_RE`.
- Produces: `_render_naver_news_collection_tab()`,
  `_show_naver_news_collection_progress(run_id)` — 다른 파일에서 참조되지 않음(순수 UI).

이 작업은 Streamlit UI라 자동 테스트가 없다(기존 정책 탭도 동일 — `views/settings.py`에
대한 pytest 커버리지 없음). Step 4를 로컬에서 앱을 띄워 직접 확인하는 수동 검증으로
대체한다.

- [ ] **Step 1: import 블록 수정**

`from utils import (...)` 블록을 교체:

```python
from utils import (
    load_collection_schedule,
    load_keywords,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    save_collection_schedule,
    save_keywords,
    save_naver_news_collection_schedule,
    save_policy_collection_schedule,
)
```

- [ ] **Step 2: 진행상황 표시 + 탭 렌더 함수 추가**

`_show_policy_collection_progress` 함수(`@st.fragment(run_every=2)` 데코레이터 포함)
바로 뒤, `def _render_policy_collection_tab():` 바로 앞에 추가:

```python
@st.fragment(run_every=2)
def _show_naver_news_collection_progress(run_id):
    logs = [l for l in db.get_run_logs(limit=500) if l["run_id"] == run_id][::-1]
    if logs:
        lines = [f"{e['brand']}: {_format_entry_status(e)}" for e in logs]
        st.code("\n".join(lines), language=None, height=200)
    if collector.active_naver_news_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(logs)}건 완료)")
    else:
        ok_count = sum(1 for e in logs if e["ok"])
        st.success(f"수집 완료: {len(logs)}건 실행, 성공 {ok_count}건")


def _render_naver_news_collection_tab():
    st.caption(
        "네이버 공식 뉴스 검색 API로 수집합니다. 키워드 관리의 키워드를 그대로 "
        "사용하며, 신규 게시물과 별도의 독립된 스케줄을 가집니다."
    )
    if not os.getenv("NAVER_CLIENT_ID") or not os.getenv("NAVER_CLIENT_SECRET"):
        st.warning(
            "⚠️ .env에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되어 있지 않습니다. "
            "네이버 개발자센터에서 애플리케이션을 등록해 값을 발급받은 뒤 .env에 "
            "추가해야 수집이 동작합니다."
        )

    st.subheader("⏰ 수집 스케줄")
    naver_news_sched_cfg = load_naver_news_collection_schedule()
    naver_news_times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(naver_news_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="naver_news_sched_times_text",
    )
    if st.button("💾 저장", key="naver_news_sched_save"):
        tokens = [t.strip() for t in naver_news_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_naver_news_collection_schedule({"times": seen})
            st.rerun()
    if naver_news_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(naver_news_sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")

    st.divider()
    running_naver_news_run_id = collector.active_naver_news_run_id()
    if running_naver_news_run_id is None:
        if st.button("🔄 지금 수집", type="primary", key="naver_news_collect_now"):
            started_run_id = collector.start_background_naver_news_collection(trigger="수동")
            if started_run_id:
                st.session_state["watched_naver_news_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 네이버뉴스 수집이 진행 중입니다.")
    else:
        st.info("🔄 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_naver_news_run_id"] = running_naver_news_run_id

    display_naver_news_run_id = running_naver_news_run_id or st.session_state.get("watched_naver_news_run_id")
    if display_naver_news_run_id:
        _show_naver_news_collection_progress(display_naver_news_run_id)

    st.divider()
    st.subheader("📜 수집 이력")
    naver_news_batches = db.get_run_batches(limit=50, channels=["네이버뉴스"])
    if naver_news_batches:
        naver_news_batch_df = pd.DataFrame(naver_news_batches)[
            ["ran_at", "trigger", "brands", "combinations", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(naver_news_batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")
```

- [ ] **Step 3: 탭 구성 및 기존 함수 수정**

`_render_data_collection()`을 교체:

```python
def _render_data_collection():
    tab_existing, tab_naver_news, tab_policy = st.tabs(
        ["📰 신규 게시물", "📡 네이버뉴스 API", "🏛️ 정부 정책"]
    )
    with tab_existing:
        _render_brand_collection_tab()
    with tab_naver_news:
        _render_naver_news_collection_tab()
    with tab_policy:
        _render_policy_collection_tab()
```

`_render_brand_collection_tab()` 안의 수집 이력 조회 줄을 교체(네이버뉴스 이력이
"신규 게시물" 이력에 섞이지 않도록):

```python
    batches = db.get_run_batches(limit=50, channels=["네이버", "구글", "다음", "커뮤니티"])
```

`_render_brand_lookup_tab()` 안의 채널 목록 줄을 교체(데이터 관리에서도 조회 가능하도록):

```python
    channels = ["전체", "네이버", "구글", "다음", "커뮤니티", "네이버뉴스"]
```

- [ ] **Step 4: 수동 검증**

로컬에서 앱 실행 후(`.env`에 임시 테스트용 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`이
없다면 경고 문구가 뜨는지부터 확인):

1. 설정 → 데이터 수집 → "📡 네이버뉴스 API" 탭이 보이는지
2. 수집 시각 저장이 동작하는지 (`data/naver_news_collection_schedule.json` 생성 확인)
3. `.env`에 실제 발급받은 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`을 넣고 "🔄 지금 수집"
   클릭 → 진행상황·수집 이력이 표시되는지
4. 설정 → 데이터 관리 → "📰 신규 게시물" 탭 채널 필터에 "네이버뉴스"가 추가되어 실제
   수집된 데이터가 조회되는지
5. "📰 신규 게시물" 탭의 자체 수집 이력에 네이버뉴스 배치가 섞이지 않는지

- [ ] **Step 5: 커밋**

```bash
git add views/settings.py
git commit -m "feat: add Naver News API collection tab to settings UI"
```

---

## 완료 후 참고

- `.env`에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 추가하는 것은 각자 로컬/서버
  환경에서 수동으로 해야 한다(`.env`는 `.gitignore`에 포함되어 커밋되지 않음). 네이버
  개발자센터(https://developers.naver.com/apps)에서 애플리케이션 등록 후 "검색" API를
  사용 설정하면 발급된다.
- 배포 시(기존 "서버 배포" 탭) `.env`도 함께 전송되는 파일 목록에 포함되어 있는지
  확인 필요 — `views/settings.py`의 `_UPLOAD_ROOT_EXTRAS = {".env"}`로 이미 포함되어
  있으므로 별도 작업 불필요.
- `mentions.url`은 채널과 무관하게 전역 UNIQUE 제약이 걸려 있어, 구글/다음 채널에서
  이미 수집된 URL이 네이버뉴스 채널로 나중에 들어오면(또는 반대 순서로) 중복으로
  간주되어 조용히 스킵된다. "네이버뉴스 탭에 신규 건수가 0건" 같은 보고는 버그가
  아니라 이 스키마 특성 때문일 수 있다.
