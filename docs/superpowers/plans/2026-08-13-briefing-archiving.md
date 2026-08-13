# 브리핑 아카이빙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 하루가 끝나면 그날의 브리핑(채널별 수집 현황·주요 뉴스·자사/경쟁사/시장 동향)을
고정된 기록으로 확정(아카이빙)해서, 이후 채널 노출 설정이나 원본 데이터 삭제와 무관하게
항상 같은 내용을 보여준다.

**Architecture:** 새 SQLite 테이블 `briefing_archives`에 하루치 콘텐츠를 JSON 컬럼으로
통째로 저장한다(참조가 아니라 표시용 내용 자체를 복사). 스케줄러가 매 tick마다 "아직
미확정인 과거 날짜"를 찾아 자동으로 확정하고(오늘은 절대 확정 안 함), 화면은 확정된
날짜면 저장된 스냅샷을, 오늘이면 지금처럼 실시간 계산을 보여준다.

**Tech Stack:** SQLite(db.py 기존 패턴), Python 표준 json 모듈, Streamlit.

**Spec:** `docs/superpowers/specs/2026-08-13-briefing-archiving-design.md`

## Global Constraints

- 한 번 확정된 날짜는 재생성 불가 (`INSERT OR IGNORE`, date가 PK).
- 확정 시점엔 채널 표시 설정(`enabled_channels`)과 무관하게 **전체 채널** 데이터를 기준으로
  계산한다.
- 아카이브에는 mention_id 참조가 아니라 표시용 필드(title/url/brand/channel/posted_at/
  signal/desc)를 그대로 복사해 저장한다 — 원본 mention이 나중에 삭제돼도 영향받지 않아야 함.
- 오늘 날짜는 절대 확정하지 않는다.
- 점수 로직은 기존 `news_feed._score()`/`build_news_items()`를 그대로 재사용한다(새로 만들지 않음).

---

### Task 1: `db.py` — briefing_archives 스키마 + insert/get 라운드트립

**Files:**
- Modify: `db.py` (상단 import, `init_db()`, 새 함수 추가)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `db.insert_briefing_archive(record: dict) -> bool`,
  `db.get_briefing_archive(date: str) -> dict | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_db.py` 맨 아래에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_db.py -k briefing_archive -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'insert_briefing_archive'`

- [ ] **Step 3: 최소 구현**

`db.py` 상단에 `import json` 추가(다른 import들과 함께, `import sqlite3` 위나 아래 아무 곳):

```python
import json
import sqlite3
```

`_ACTIVITY_LOG_SQL` 정의 바로 아래(105번째 줄 근방, `def _mention_vectors_sql()` 이전)에 추가:

```python
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
```

`init_db()` 안, `con.execute(_ACTIVITY_LOG_SQL)` 바로 다음 줄에 추가:

```python
        con.execute(_BRIEFING_ARCHIVES_SQL)
```

`insert_mention`/`insert_run_log` 등이 정의된 영역 아무 곳(파일 뒤쪽 적당한 곳)에 새 함수 추가:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_db.py -k briefing_archive -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_db.py
git commit -m "feat: briefing_archives 테이블 + insert/get 함수 추가"
```

---

### Task 2: `db.py` — 쿼리 헬퍼 (미확정 날짜 판단용)

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: 없음 (Task 1과 독립적인 `mentions`/`briefing_archives` 조회)
- Produces: `db.get_archived_briefing_dates() -> set[str]`,
  `db.get_earliest_mention_date() -> str | None`,
  `db.get_mentions_by_collected_date(date: str) -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_db.py`에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_db.py -k "archived_briefing_dates or earliest_mention or by_collected_date" -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: 최소 구현**

`db.py`에 (Task 1에서 추가한 함수들 아래) 추가:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_db.py -k "archived_briefing_dates or earliest_mention or by_collected_date" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_db.py
git commit -m "feat: 브리핑 아카이빙용 조회 헬퍼(get_archived_briefing_dates 등) 추가"
```

---

### Task 3: `news_feed.py` — 브랜드 역할 헬퍼 + 아카이브 콘텐츠 계산

**Files:**
- Modify: `news_feed.py:167-185` (`build_news_items`의 `items.append(...)` 블록에 필드 2개
  추가), `news_feed.py` (파일 하단에 새 함수 3개 추가)
- Test: `tests/test_news_feed.py`

**Interfaces:**
- Consumes: `news_feed.build_news_items(mentions, own_brands, now=None) -> list[dict]` (기존)
- Produces: `news_feed.competitor_brand_names() -> set`, `news_feed.market_brand_names() -> set`,
  `news_feed.build_briefing_archive_content(mentions, own_brands, competitor_brands, market_brands, now=None) -> dict`
  (반환 dict 키: `channel_counts`, `channel_top_news`, `own_brand_news`, `competitor_news`,
  `market_news`, `total_count`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_news_feed.py`에 추가:

```python
def test_competitor_brand_names_returns_only_competitor_role(monkeypatch):
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": [
        {"name": "프롭티어", "role": "own"},
        {"name": "직방", "role": "competitor"},
        {"name": "AI", "role": "market"},
    ]})

    assert news_feed.competitor_brand_names() == {"직방"}


def test_market_brand_names_returns_only_market_role(monkeypatch):
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": [
        {"name": "프롭티어", "role": "own"},
        {"name": "직방", "role": "competitor"},
        {"name": "AI", "role": "market"},
    ]})

    assert news_feed.market_brand_names() == {"AI"}


def _mention_full(title, brand, channel, collected_at, mention_id):
    return {
        "id": mention_id, "title": title, "brand": brand, "url": f"https://x/{mention_id}",
        "collected_at": collected_at, "snippet": "", "content": "", "summary": "",
        "channel": channel, "posted_at": "2026.08.10",
    }


def test_build_news_items_includes_channel_and_posted_at_fields():
    mentions = [_mention_full("제목", "직방", "네이버뉴스API", "2026-08-10 09:00:00", 1)]

    items = news_feed.build_news_items(mentions, own_brands=set())

    assert items[0]["channel"] == "네이버뉴스API"
    assert items[0]["posted_at"] == "2026.08.10"


def test_build_briefing_archive_content_splits_by_brand_role():
    mentions = [
        _mention_full("프롭티어 신규 서비스", "프롭티어", "네이버", "2026-08-10 09:00:00", 1),
        _mention_full("직방 매물 공개", "직방", "구글", "2026-08-10 10:00:00", 2),
        _mention_full("AI 시장 동향", "AI", "매경API", "2026-08-10 11:00:00", 3),
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands={"프롭티어"}, competitor_brands={"직방"}, market_brands={"AI"},
    )

    assert result["own_brand_news"][0]["title"] == "프롭티어 신규 서비스"
    assert result["competitor_news"][0]["title"] == "직방 매물 공개"
    assert result["market_news"][0]["title"] == "AI 시장 동향"
    assert result["total_count"] == 3


def test_build_briefing_archive_content_channel_counts_and_top_news():
    mentions = [
        _mention_full("기사1", "직방", "네이버", "2026-08-10 09:00:00", 1),
        _mention_full("기사2", "다방", "네이버", "2026-08-10 10:00:00", 2),
        _mention_full("기사3", "직방", "구글", "2026-08-10 11:00:00", 3),
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands=set(), competitor_brands={"직방", "다방"}, market_brands=set(),
    )

    assert result["channel_counts"] == {"네이버": 2, "구글": 1}
    assert len(result["channel_top_news"]["네이버"]) == 2
    assert len(result["channel_top_news"]["구글"]) == 1


def test_build_briefing_archive_content_limits_each_section_to_top_n():
    mentions = [
        _mention_full(f"직방 기사{i}", "직방", "네이버", f"2026-08-10 0{i}:00:00", i)
        for i in range(1, 8)
    ]

    result = news_feed.build_briefing_archive_content(
        mentions, own_brands=set(), competitor_brands={"직방"}, market_brands=set(),
    )

    assert len(result["competitor_news"]) == 5
    assert len(result["channel_top_news"]["네이버"]) == 3
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_news_feed.py -k "competitor_brand or market_brand or archive_content or channel_and_posted_at" -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: 최소 구현**

`news_feed.py`의 `build_news_items` 안 `items.append({...})` 블록(기존 168번째 줄 근방)에
두 필드 추가 — 기존 필드는 그대로 두고 아래 두 줄만 끼워 넣는다:

```python
        items.append({
            "score": _score(m, categories, own_brands, now),
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "channel": m.get("channel", ""),
            "posted_at": m.get("posted_at", ""),
            "date": collected.strftime("%Y-%m-%d") if collected else (m.get("collected_at", "") or "")[:10],
            "firm": m.get("brand", ""),
            "collected_at": m.get("collected_at", ""),
            "categories": categories,
            "signal": _signal_label(categories),
            "desc": desc,
            "desc_long": desc_long,
            "mention_id": m.get("id"),
            "content": content,
            "summary": summary,
            "has_real_content": has_real_content,
            "decision": [f"{cat_line} {recency_line}"],
            "meta": f"🕒 {m.get('posted_at') or (m.get('collected_at', '') or '')[:16]} · {m.get('channel', '')}",
            "_collected": collected,
        })
```

`news_feed.py` 파일 맨 아래(`build_briefings` 함수 뒤)에 추가:

```python
def competitor_brand_names() -> set:
    return {b["name"] for b in load_keywords().get("brands", []) if b.get("role") == "competitor"}


def market_brand_names() -> set:
    return {b["name"] for b in load_keywords().get("brands", []) if b.get("role") == "market"}


def _archive_item(it: dict) -> dict:
    return {
        "title": it["title"], "url": it["url"], "brand": it["firm"], "channel": it["channel"],
        "posted_at": it["posted_at"], "signal": it["signal"],
        "desc": it["desc"][0] if it["desc"] else "",
    }


def build_briefing_archive_content(
    mentions: list[dict], own_brands: set, competitor_brands: set, market_brands: set,
    now: datetime | None = None,
) -> dict:
    """하루치 mentions를 채널별 수집 현황/주요 뉴스, 자사/경쟁사/시장 동향으로 가공한다.
    build_news_items()로 매긴 점수(카테고리 매칭·최근성·자사 가산)를 그대로 재사용해
    채널별/역할별 상위 항목만 골라 담는다. 아카이브에는 mention_id가 아니라 표시용 필드를
    그대로 복사해 저장하므로, 원본 mention이 나중에 삭제돼도 이 결과는 영향받지 않는다."""
    items = build_news_items(mentions, own_brands, now=now)

    channel_counts: dict[str, int] = {}
    channel_items: dict[str, list] = {}
    for it in items:
        ch = it["channel"]
        channel_counts[ch] = channel_counts.get(ch, 0) + 1
        channel_items.setdefault(ch, []).append(it)

    channel_top_news = {
        ch: [_archive_item(it) for it in group[:3]] for ch, group in channel_items.items()
    }

    def _top_by_brand(brand_set: set) -> list:
        return [_archive_item(it) for it in items if it["firm"] in brand_set][:5]

    return {
        "channel_counts": channel_counts,
        "channel_top_news": channel_top_news,
        "own_brand_news": _top_by_brand(own_brands),
        "competitor_news": _top_by_brand(competitor_brands),
        "market_news": _top_by_brand(market_brands),
        "total_count": len(items),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_news_feed.py -v`
Expected: PASS 전체 (기존 테스트 포함 — `channel`/`posted_at` 필드 추가는 기존 키를 안
건드리므로 회귀 없어야 함)

- [ ] **Step 5: 커밋**

```bash
git add news_feed.py tests/test_news_feed.py
git commit -m "feat: 브리핑 아카이브 콘텐츠 계산(build_briefing_archive_content) 추가"
```

---

### Task 4: `news_feed.py` — 확정 오케스트레이션(archive_pending_briefings)

**Files:**
- Modify: `news_feed.py` (상단 import, 파일 하단에 함수 추가)
- Test: `tests/test_news_feed.py`

**Interfaces:**
- Consumes: `db.get_earliest_mention_date()`, `db.get_archived_briefing_dates()`,
  `db.get_mentions_by_collected_date(date)`, `db.insert_briefing_archive(record)` (Task 1/2),
  `build_briefing_archive_content(...)`(Task 3), `own_brand_names()`(기존),
  `competitor_brand_names()`/`market_brand_names()`(Task 3)
- Produces: `news_feed.archive_pending_briefings() -> list[str]` (새로 확정된 날짜 목록)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_news_feed.py` 맨 위 두 줄(`from datetime import datetime` / `import news_feed`)을
아래로 교체:

```python
from datetime import date, datetime

import db
import news_feed
```

파일 하단에 테스트 추가:

```python
def test_archive_pending_briefings_archives_all_past_unarchived_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": [
        {"name": "직방", "role": "competitor"},
    ]})
    db.insert_mention({
        "brand": "직방", "channel": "네이버", "source_detail": "", "title": "제목1",
        "url": "https://x/1", "snippet": "", "posted_at": "", "collected_at": "2026-08-10 09:00:00",
    })
    db.insert_mention({
        "brand": "직방", "channel": "네이버", "source_detail": "", "title": "제목2",
        "url": "https://x/2", "snippet": "", "posted_at": "", "collected_at": "2026-08-11 09:00:00",
    })

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 12)

    monkeypatch.setattr(news_feed, "date", _FixedDate)

    archived = news_feed.archive_pending_briefings()

    assert set(archived) == {"2026-08-10", "2026-08-11"}
    assert db.get_briefing_archive("2026-08-10") is not None
    assert db.get_briefing_archive("2026-08-11") is not None


def test_archive_pending_briefings_never_archives_today(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": []})
    db.insert_mention({
        "brand": "직방", "channel": "네이버", "source_detail": "", "title": "제목1",
        "url": "https://x/1", "snippet": "", "posted_at": "", "collected_at": "2026-08-12 09:00:00",
    })

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 12)

    monkeypatch.setattr(news_feed, "date", _FixedDate)

    archived = news_feed.archive_pending_briefings()

    assert archived == []
    assert db.get_briefing_archive("2026-08-12") is None


def test_archive_pending_briefings_skips_already_archived_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": []})
    db.insert_mention({
        "brand": "직방", "channel": "네이버", "source_detail": "", "title": "제목1",
        "url": "https://x/1", "snippet": "", "posted_at": "", "collected_at": "2026-08-10 09:00:00",
    })

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 12)

    monkeypatch.setattr(news_feed, "date", _FixedDate)
    news_feed.archive_pending_briefings()

    archived_again = news_feed.archive_pending_briefings()

    assert archived_again == []


def test_archive_pending_briefings_returns_empty_when_no_mentions_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(news_feed, "load_keywords", lambda: {"brands": []})

    assert news_feed.archive_pending_briefings() == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_news_feed.py -k archive_pending_briefings -v`
Expected: FAIL — `AttributeError: module 'news_feed' has no attribute 'archive_pending_briefings'`

- [ ] **Step 3: 최소 구현**

`news_feed.py` 상단 import 수정:

```python
from datetime import date, datetime, timedelta
```

(기존 `from datetime import datetime, timedelta`에 `date` 추가)

같은 파일 상단, `from utils import load_channel_visibility, load_keywords` 아래에 추가:

```python
import db
```

`news_feed.py` 파일 맨 아래(Task 3에서 추가한 함수들 뒤)에 추가:

```python
def archive_pending_briefings() -> list[str]:
    """가장 이른 mention 수집일부터 어제까지, 아직 확정 안 된 날짜를 전부 찾아 하나씩
    아카이브한다. 오늘 날짜는 절대 확정하지 않는다(아직 진행 중이므로). 새로 확정된
    날짜 목록을 반환한다 — 최초 실행 시에는 그동안 쌓인 과거 날짜 전부가 한 번에
    소급 확정된다."""
    earliest = db.get_earliest_mention_date()
    if earliest is None:
        return []

    today = date.today()
    yesterday = today - timedelta(days=1)
    start = datetime.strptime(earliest, "%Y-%m-%d").date()
    if start > yesterday:
        return []

    already_archived = db.get_archived_briefing_dates()
    own_brands = own_brand_names()
    competitor_brands = competitor_brand_names()
    market_brands = market_brand_names()

    newly_archived = []
    current = start
    while current <= yesterday:
        date_str = current.strftime("%Y-%m-%d")
        if date_str not in already_archived:
            day_mentions = db.get_mentions_by_collected_date(date_str)
            if day_mentions:
                content = build_briefing_archive_content(
                    day_mentions, own_brands, competitor_brands, market_brands,
                )
                record = {
                    "date": date_str,
                    "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    **content,
                }
                if db.insert_briefing_archive(record):
                    newly_archived.append(date_str)
        current += timedelta(days=1)
    return newly_archived
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_news_feed.py -v`
Expected: PASS 전체

- [ ] **Step 5: 커밋**

```bash
git add news_feed.py tests/test_news_feed.py
git commit -m "feat: 미확정 과거 날짜 브리핑 자동 확정(archive_pending_briefings) 추가"
```

---

### Task 5: `scheduler.py` — 자동 확정 tick 연결

**Files:**
- Modify: `scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `news_feed.archive_pending_briefings() -> list[str]` (Task 4)
- Produces: `scheduler._tick_archive_briefings() -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_scheduler.py`의 `_reset()` 함수를 찾아 아래 두 줄을 추가(다른 무관 tick들을
비활성화하는 기존 줄 바로 옆에 — 이렇게 안 하면 기존 `_tick()` 테스트들이 실제
`news_feed.archive_pending_briefings()`를 호출해 격리 안 된 진짜 DB를 건드리게 된다):

```python
def _reset(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_fired", "")
    monkeypatch.setattr(scheduler, "_last_fired_policy", "")
    monkeypatch.setattr(scheduler, "_last_fired_naver_news", "")
    monkeypatch.setattr(scheduler, "_last_fired_mk_news", "")
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": []})
    # 신규 게시물/정책/네이버뉴스 스케줄과 무관한 PDF 요약 미리 생성/자동 벡터화/브리핑
    # 아카이빙 tick은 실제 Gemini/DB를 건드리므로, 이 tick들을 직접 테스트하는 케이스가
    # 아니면 아무 일도 하지 않게 한다.
    monkeypatch.setattr(scheduler, "_tick_pdf_presummary", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_auto_vectorize", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_archive_briefings", lambda: None)
```

(마지막 줄 `_tick_archive_briefings` 추가가 이 스텝의 핵심 변경.)

파일 하단에 테스트 추가:

```python
def test_tick_archive_briefings_calls_archive_pending_briefings(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler.news_feed, "archive_pending_briefings", lambda: calls.append(1) or ["2026-08-10"]
    )

    scheduler._tick_archive_briefings()

    assert calls == [1]


def test_tick_archive_briefings_swallows_exception(monkeypatch, caplog):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler.news_feed, "archive_pending_briefings", boom)

    with caplog.at_level("ERROR", logger="hana_p.scheduler"):
        scheduler._tick_archive_briefings()

    assert any("오류" in record.message for record in caplog.records)


def test_tick_includes_archive_briefings_when_not_disabled(monkeypatch):
    """_reset()의 비활성화 없이 _tick()을 직접 호출하면 브리핑 아카이빙 tick도 함께 도는지
    확인 — _tick()에 실제로 연결됐는지 검증하는 목적."""
    monkeypatch.setattr(scheduler, "_last_fired", "")
    monkeypatch.setattr(scheduler, "_last_fired_policy", "")
    monkeypatch.setattr(scheduler, "_last_fired_naver_news", "")
    monkeypatch.setattr(scheduler, "_last_fired_mk_news", "")
    monkeypatch.setattr(scheduler, "load_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_policy_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_naver_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "load_mk_news_collection_schedule", lambda: {"times": []})
    monkeypatch.setattr(scheduler, "_tick_pdf_presummary", lambda: None)
    monkeypatch.setattr(scheduler, "_tick_auto_vectorize", lambda: None)
    calls = []
    monkeypatch.setattr(scheduler.news_feed, "archive_pending_briefings", lambda: calls.append(1) or [])

    scheduler._tick()

    assert calls == [1]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_scheduler.py -k archive_briefings -v`
Expected: FAIL — `AttributeError: module 'scheduler' has no attribute '_tick_archive_briefings'`

- [ ] **Step 3: 최소 구현**

`scheduler.py` 상단 import에 추가:

```python
import collector
import news_feed
import summarizer
import vectorizer
```

(기존 `import collector` / `import summarizer` / `import vectorizer` 사이에 `import news_feed`
한 줄만 끼워 넣으면 됨 — alphabetical 순서 유지)

`_tick_mk_news()` 함수 뒤, `_tick_pdf_presummary()` 함수 앞에 추가:

```python
def _tick_archive_briefings() -> None:
    """일별 브리핑 확정(아카이빙). 정확한 시각 일치가 아니라 "아직 확정 안 된 과거
    날짜가 있으면 즉시 확정"하는 방식이라 tick을 놓쳐도 다음 tick에서 만회된다."""
    try:
        archived = news_feed.archive_pending_briefings()
        if archived:
            logger.info("브리핑 아카이빙 완료: %s", ", ".join(sorted(archived)))
    except Exception:
        logger.exception("스케줄러(브리핑 아카이빙) 반복 실행 중 오류 발생")
```

`_tick()` 함수를 아래처럼 수정:

```python
def _tick() -> None:
    """스케줄러 한 사이클 분량의 로직. 신규 게시물/정부 정책/네이버뉴스 API/매경 API는
    각자 독립된 스케줄로 체크하고, 브리핑 아카이빙은 스케줄과 무관하게 매 tick 확인한다."""
    _tick_new_posts()
    _tick_policy()
    _tick_naver_news()
    _tick_mk_news()
    _tick_archive_briefings()
    _tick_pdf_presummary()
    _tick_auto_vectorize()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS 전체 (기존 테스트 포함 — `_reset()`이 새 tick을 비활성화하므로 회귀 없어야 함)

- [ ] **Step 5: 커밋**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: 브리핑 아카이빙 스케줄러 tick 연결"
```

---

### Task 6: `views/briefings.py` — 화면 교체

**Files:**
- Modify: `views/briefings.py` (전체 교체)

**Interfaces:**
- Consumes: `db.get_archived_briefing_dates()`, `db.get_briefing_archive(date)` (Task 1/2),
  `news_feed.build_briefing_archive_content(...)`, `news_feed.own_brand_names()`,
  `news_feed.competitor_brand_names()`, `news_feed.market_brand_names()` (Task 3),
  `news_feed.enabled_channels()`/`news_feed.BROAD_LIMIT`(기존), `cached_db.get_mentions(...)`(기존)
- Produces: 없음(화면 렌더 함수, 다른 코드가 가져다 쓰지 않음)

- [ ] **Step 1: 전체 파일 교체**

`views/briefings.py` 전체를 아래 내용으로 교체:

```python
from datetime import date

import pandas as pd
import streamlit as st

import cached_db
import db
import news_feed
import theme


def _render_news_list(title: str, items: list) -> None:
    st.markdown(f"#### {title}")
    if not items:
        st.caption("해당 소식 없음")
        return
    for it in items:
        st.markdown(f"- [{it['title']}]({it['url']}) · {it['brand']} · {it['posted_at']}")
        if it.get("desc"):
            st.caption(it["desc"])


def _render_sections(date_str: str, content: dict) -> None:
    st.markdown(f"### {date_str}")
    st.caption(f"총 {content['total_count']:,}건 수집")

    st.markdown("#### 📡 채널별 수집 현황")
    counts = sorted(content["channel_counts"].items(), key=lambda kv: -kv[1])
    if counts:
        counts_df = pd.DataFrame([{"채널": ch, "건수": n} for ch, n in counts])
        st.dataframe(counts_df, use_container_width=True, hide_index=True)
    else:
        st.caption("수집된 데이터 없음")

    st.markdown("#### 📰 채널별 주요 뉴스")
    for ch, items in content["channel_top_news"].items():
        with st.expander(f"{ch} ({len(items)}건)"):
            for it in items:
                st.markdown(f"- [{it['title']}]({it['url']}) · {it['brand']} · {it['posted_at']}")

    _render_news_list("🏠 프롭티어 관련 뉴스", content["own_brand_news"])
    _render_news_list("⚔️ 경쟁사 동향", content["competitor_news"])
    _render_news_list("🌐 시장 동향", content["market_news"])


def render():
    archived_dates = sorted(db.get_archived_briefing_dates(), reverse=True)
    today_str = date.today().strftime("%Y-%m-%d")

    live_mentions = cached_db.get_mentions(
        limit=news_feed.BROAD_LIMIT, channels=tuple(news_feed.enabled_channels())
    )
    today_mentions = [m for m in live_mentions if (m.get("collected_at") or "")[:10] == today_str]
    has_today = bool(today_mentions)

    dates = ([today_str] if has_today else []) + [d for d in archived_dates if d != today_str]

    if not dates:
        theme.hero("\U0001F4DD 브리핑 아카이브", "아직 수집된 데이터가 없습니다")
        st.info("설정 → 데이터 수집에서 수집을 먼저 실행해주세요.")
        theme.footer("실데이터 연동 · 수집 대기 중")
        return

    theme.hero(
        "\U0001F4DD 브리핑 아카이브",
        f"확정된 브리핑 {len(archived_dates):,}건 · 왼쪽 목록에서 날짜를 고르세요",
    )

    if "briefing_date_idx" not in st.session_state or st.session_state.briefing_date_idx >= len(dates):
        st.session_state.briefing_date_idx = 0

    list_col, panel_col = st.columns([1, 2.4])

    with list_col:
        for i, d in enumerate(dates):
            selected = i == st.session_state.briefing_date_idx
            prefix = "\U0001F449 " if selected else ""
            label = f"{d} (진행중)" if d == today_str and has_today else d
            if st.button(f"{prefix}{label}", key=f"bf_{i}", use_container_width=True):
                st.session_state.briefing_date_idx = i
                st.rerun()

    with panel_col:
        picked_date = dates[st.session_state.briefing_date_idx]
        if picked_date == today_str and has_today:
            st.info("\U0001F504 오늘은 아직 진행 중입니다 — 자정이 지나면 자동으로 확정됩니다.")
            content = news_feed.build_briefing_archive_content(
                today_mentions, news_feed.own_brand_names(),
                news_feed.competitor_brand_names(), news_feed.market_brand_names(),
            )
            _render_sections(today_str, content)
        else:
            archive = db.get_briefing_archive(picked_date)
            _render_sections(archive["date"], archive)

    theme.footer("확정된 날짜는 고정 기록 · 오늘은 실시간 집계")
```

- [ ] **Step 2: 로컬 서버로 수동 확인**

뷰 레이어는 이 프로젝트 관례상 자동 테스트가 없다(다른 `views/*.py`와 동일). 로컬 서버를
재시작하고 다음을 직접 확인한다:

1. `streamlit run app.py --server.address 192.168.14.222 --server.port 7000` 재시작
2. "브리핑" 메뉴 진입 — 날짜 목록에 "오늘 (진행중)"과 과거 날짜들이 보이는지 확인
3. 아직 과거 날짜가 하나도 확정 안 됐다면(최초 배포 직후), 스케줄러가 첫 tick(30초 이내)에
   돌 때까지 기다렸다가 새로고침 — 과거 날짜들이 나타나야 함
4. 과거 날짜 하나를 선택 — 채널별 수집 현황 표, 채널별 주요 뉴스, 프롭티어/경쟁사/시장
   섹션이 모두 보이는지 확인
5. 설정 → 데이터 수집 하단에서 채널 표시 토글을 하나 껐다 켰다 한 뒤, 같은 과거 날짜를
   다시 열어서 **내용이 전혀 안 바뀌는지** 확인 (이번 작업의 핵심 검증 포인트)
6. "오늘" 날짜는 계속 실시간으로 바뀌는지(수집 후 새로고침하면 건수가 늘어나는지) 확인

- [ ] **Step 3: 커밋**

```bash
git add views/briefings.py
git commit -m "feat: 브리핑 화면을 확정 아카이브 기반으로 교체"
```

---

## 최종 확인

모든 태스크 완료 후 전체 테스트 스위트 실행:

```bash
python -m pytest -q
```

Expected: 전부 PASS, 실패 0건.
