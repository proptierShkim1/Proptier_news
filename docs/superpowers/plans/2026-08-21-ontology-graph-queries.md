# 온톨로지 + 그래프SQL 쿼리 도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI AGENT가 뉴스카테고리와 정책카테고리를 엮어 답할 수 없던 질문(정책 발표 전후 뉴스 변화, 카테고리 간 동시 발생, 브랜드 role별 카테고리 분포)에 답할 수 있도록, 정적 온톨로지 선언 + 3개의 그래프형 쿼리 도구를 추가한다.

**Architecture:** `ontology.py`가 뉴스카테고리↔정책카테고리 정렬을 정적으로 선언한다. `graph_queries.py`가 그 선언과 기존 `cached_db`/`news_feed.categorize`/`policy_feed.categorize`를 조합해 3개의 조회 함수를 제공한다(Python 레벨 조인, SQL `JOIN`이나 스키마 변경 없음). `agent_chat.py`가 이 3개 함수를 `_STATS_TOOLS`에 등록해 Gemini automatic function calling으로 노출한다.

**Tech Stack:** Python, pytest, `google-genai` SDK(automatic function calling, 함수 docstring이 도구 스키마), 기존 SQLite(`db.py`)/`st.cache_data` 60초 TTL 캐시(`cached_db.py`).

**Spec:** `docs/superpowers/specs/2026-08-21-ontology-graph-queries-design.md`

## Global Constraints

- DB 스키마 변경 없음 — `mentions`/`policy_events`에 컬럼을 추가하지 않는다.
- 카테고리 계산은 항상 기존 `news_feed.categorize(text)` / `policy_feed.categorize(title)`를 재사용한다 — 새 분류 로직을 만들지 않는다.
- DB 조회는 항상 `cached_db.*`를 거친다 — `db.py`를 직접 호출하지 않는다(다중 사용자 대비 60초 TTL 캐시 원칙, [[project_ai_agent_multiuser_perf_2026-08-19]]).
- `_STATS_TOOLS`에 들어가는 함수는 기존 컨벤션대로 try/except 없이 plain dict/list를 반환하고, Args/Returns를 한국어로 구체적으로 쓴 docstring을 가진다(그 독스트링이 Gemini function calling 스키마로 그대로 쓰인다).
- 새 테스트는 `tests/test_agent_chat.py`의 컨벤션(`monkeypatch.setattr(<module>.cached_db, "...", lambda days: ...)`으로 DB 계층을 고정값으로 대체)을 따른다.

---

### Task 1: `ontology.py` — 뉴스카테고리 ↔ 정책카테고리 정렬 선언

**Files:**
- Create: `ontology.py`
- Test: `tests/test_ontology.py`

**Interfaces:**
- Produces: `ontology.CATEGORY_ALIGNMENT: dict[str, list[str]]`, `ontology.aligned_policy_categories(news_category: str) -> list[str]`, `ontology.aligned_news_categories(policy_category: str) -> list[str]` — Task 2/3에서 그대로 씀.

- [ ] **Step 1: Write the failing tests**

`tests/test_ontology.py`:
```python
import ontology


def test_aligned_policy_categories_known_news_category():
    assert ontology.aligned_policy_categories("정책") == ["규제·법령", "지원·사업"]


def test_aligned_policy_categories_unknown_returns_empty():
    assert ontology.aligned_policy_categories("해외") == []


def test_aligned_news_categories_known_policy_category():
    assert ontology.aligned_news_categories("지원·사업") == ["정책", "매물"]


def test_aligned_news_categories_unknown_returns_empty():
    assert ontology.aligned_news_categories("조직·인사") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ontology.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ontology'`

- [ ] **Step 3: Write the implementation**

`ontology.py`:
```python
"""
hana_p — 뉴스카테고리/정책카테고리처럼 서로 다른 분류 체계 사이의 정적 관계(온톨로지)를
선언한다. 브랜드 role(own/competitor/market)은 이미 keywords.json에 있으므로 여기서
다시 선언하지 않는다. 관계 수가 적어(수십 개 수준) DB 테이블이 아니라 사람이 직접
읽고 고칠 수 있는 이 파일로 선언한다.
"""

CATEGORY_ALIGNMENT: dict[str, list[str]] = {
    "정책": ["규제·법령", "지원·사업"],
    "매물": ["지원·사업"],
    "시세·감정": ["통계·조사"],
}


def aligned_policy_categories(news_category: str) -> list[str]:
    """뉴스카테고리에 대응되는 정책카테고리 목록. 대응이 없으면 빈 리스트."""
    return CATEGORY_ALIGNMENT.get(news_category, [])


def aligned_news_categories(policy_category: str) -> list[str]:
    """정책카테고리에 대응되는 뉴스카테고리 목록(CATEGORY_ALIGNMENT을 역방향으로 조회).
    대응이 없으면 빈 리스트."""
    return [
        news_category
        for news_category, policy_categories in CATEGORY_ALIGNMENT.items()
        if policy_category in policy_categories
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ontology.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ontology.py tests/test_ontology.py
git commit -m "feat: 뉴스-정책 카테고리 정렬 온톨로지 선언 추가"
```

---

### Task 2: `graph_queries.py` — `category_alignment_counts`

**Files:**
- Create: `graph_queries.py`
- Test: `tests/test_graph_queries.py`

**Interfaces:**
- Consumes: `ontology.aligned_policy_categories`, `ontology.aligned_news_categories` (Task 1); `cached_db.get_mentions_since(days: int) -> list[dict]`, `cached_db.get_policy_events_since(days: int) -> list[dict]` (기존); `news_feed.categorize(text: str) -> list[str]`, `policy_feed.categorize(title: str) -> list[str]` (기존).
- Produces: `graph_queries.category_alignment_counts(news_category="", policy_category="", days=30) -> dict | list[dict]` — Task 5에서 `_STATS_TOOLS`에 등록.

- [ ] **Step 1: Write the failing tests**

`tests/test_graph_queries.py`:
```python
import graph_queries


def test_category_alignment_counts_for_news_category(monkeypatch):
    mentions = [
        {"title": "국토부 정책 발표", "snippet": ""},
        {"title": "전세 매물 급증", "snippet": ""},
    ]
    events = [
        {"title": "전월세 신고제 시행령 개정"},
        {"title": "임대주택 지원 사업 확대"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)

    result = graph_queries.category_alignment_counts(news_category="정책", days=30)

    assert result == {
        "news_category": "정책",
        "aligned_policy_categories": ["규제·법령", "지원·사업"],
        "news_count": 1,
        "policy_counts": {"규제·법령": 1, "지원·사업": 1},
        "days": 30,
    }


def test_category_alignment_counts_for_policy_category(monkeypatch):
    mentions = [
        {"title": "전세 매물 급증", "snippet": ""},
        {"title": "국토부 정책 발표", "snippet": ""},
    ]
    events = [{"title": "임대주택 지원 사업 확대"}]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)

    result = graph_queries.category_alignment_counts(policy_category="지원·사업", days=30)

    assert result == {
        "policy_category": "지원·사업",
        "aligned_news_categories": ["정책", "매물"],
        "policy_count": 1,
        "news_counts": {"정책": 1, "매물": 1},
        "days": 30,
    }


def test_category_alignment_counts_returns_all_pairs_when_no_filter(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(days=30)

    assert [pair["news_category"] for pair in result] == ["정책", "매물", "시세·감정"]


def test_category_alignment_counts_unknown_news_category_returns_empty_alignment(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(news_category="해외", days=30)

    assert result["aligned_policy_categories"] == []
    assert result["policy_counts"] == {}


def test_category_alignment_counts_prefers_news_category_when_both_given(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: [])
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.category_alignment_counts(
        news_category="정책", policy_category="지원·사업", days=30
    )

    assert result["news_category"] == "정책"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph_queries'`

- [ ] **Step 3: Write the implementation**

`graph_queries.py`:
```python
"""
hana_p — ontology.py의 정적 관계와 cached_db/categorize()를 조합해, mentions와
policy_events를 카테고리·날짜 기준으로 엮는 조회 함수(그래프형 쿼리)를 제공한다.
SQL JOIN이나 스키마 변경 없이 Python 레벨에서 조인한다 — 자세한 배경은
docs/superpowers/specs/2026-08-21-ontology-graph-queries-design.md 참고.
"""

from datetime import date, datetime, timedelta

import cached_db
import news_feed
import ontology
import policy_feed
import utils


def _today() -> date:
    return date.today()


def _mention_count_for_category(mentions: list[dict], category: str) -> int:
    return sum(
        1
        for m in mentions
        if category in news_feed.categorize(f"{m.get('title', '')} {m.get('snippet', '')}")
    )


def _policy_count_for_category(events: list[dict], category: str) -> int:
    return sum(1 for e in events if category in policy_feed.categorize(e.get("title", "")))


def _news_category_alignment(news_category: str, days: int) -> dict:
    aligned = ontology.aligned_policy_categories(news_category)
    mentions = cached_db.get_mentions_since(days)
    events = cached_db.get_policy_events_since(days)
    return {
        "news_category": news_category,
        "aligned_policy_categories": aligned,
        "news_count": _mention_count_for_category(mentions, news_category),
        "policy_counts": {pc: _policy_count_for_category(events, pc) for pc in aligned},
        "days": days,
    }


def _policy_category_alignment(policy_category: str, days: int) -> dict:
    aligned = ontology.aligned_news_categories(policy_category)
    mentions = cached_db.get_mentions_since(days)
    events = cached_db.get_policy_events_since(days)
    return {
        "policy_category": policy_category,
        "aligned_news_categories": aligned,
        "policy_count": _policy_count_for_category(events, policy_category),
        "news_counts": {nc: _mention_count_for_category(mentions, nc) for nc in aligned},
        "days": days,
    }


def category_alignment_counts(
    news_category: str = "", policy_category: str = "", days: int = 30
) -> dict | list[dict]:
    """뉴스카테고리와 정책카테고리 중 서로 대응되는(온톨로지로 정렬된) 카테고리가 최근
    며칠간 각각 몇 건씩 나왔는지 알려준다 — "정책 카테고리별로 요즘 어떤 뉴스카테고리가
    같이 뜨고 있어?" 같은, 두 분류 체계를 엮는 질문에 쓴다.

    Args:
        news_category: 조회할 뉴스카테고리(신규 도입/AI/부동산AI/매물/시세·감정/정책/
            해외/리포트 중 하나). 지정하면 대응되는 정책카테고리들의 건수를 함께 반환.
        policy_category: 조회할 정책카테고리(규제·법령/지원·사업/통계·조사/조직·인사/
            행사·홍보 중 하나). news_category가 없을 때만 쓰이며, 지정하면 대응되는
            뉴스카테고리들의 건수를 함께 반환.
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        news_category를 줬으면 {"news_category": str, "aligned_policy_categories":
        list[str], "news_count": int, "policy_counts": {정책카테고리: int, ...},
        "days": int}. policy_category만 줬으면 {"policy_category": str,
        "aligned_news_categories": list[str], "policy_count": int, "news_counts":
        {뉴스카테고리: int, ...}, "days": int}. 둘 다 안 주면 온톨로지에 선언된 모든
        뉴스카테고리 각각에 대해 위 news_category 형태의 딕셔너리를 담은 리스트.
        대응되는 카테고리가 없으면 aligned_* 리스트가 빈 채로 정상 반환된다.
    """
    if news_category:
        return _news_category_alignment(news_category, days)
    if policy_category:
        return _policy_category_alignment(policy_category, days)
    return [_news_category_alignment(nc, days) for nc in ontology.CATEGORY_ALIGNMENT]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph_queries.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add graph_queries.py tests/test_graph_queries.py
git commit -m "feat: 뉴스-정책 카테고리 정렬 건수 조회 도구(category_alignment_counts) 추가"
```

---

### Task 3: `graph_queries.py` — `policy_event_mention_impact`

**Files:**
- Modify: `graph_queries.py` (Task 2에서 만든 파일에 함수 추가)
- Test: `tests/test_graph_queries.py` (추가)

**Interfaces:**
- Consumes: Task 1의 `ontology.aligned_news_categories`; 기존 `cached_db.get_policy_events_since`/`get_mentions_since`, `policy_feed.categorize`, `news_feed.categorize`.
- Produces: `graph_queries.policy_event_mention_impact(policy_keyword: str, before_days: int = 7, after_days: int = 7) -> dict`, 테스트에서 monkeypatch할 `graph_queries._today() -> date` (Task 2에서 이미 정의됨).

- [ ] **Step 1: Write the failing tests**

`tests/test_graph_queries.py`에 추가:
```python
from datetime import date


def test_policy_event_mention_impact_not_found(monkeypatch):
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: [])

    result = graph_queries.policy_event_mention_impact("전세사기")

    assert result == {"found": False, "policy_keyword": "전세사기"}


def test_policy_event_mention_impact_found_counts_before_after(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"}]
    mentions = [
        {"title": "국토부 정책 발표", "snippet": "", "collected_at": "2026-08-05"},
        {"title": "정책 대책 발표", "snippet": "", "collected_at": "2026-08-12"},
        {"title": "정책 제도 개편", "snippet": "", "collected_at": "2026-08-14"},
        {"title": "전세 매물 정보", "snippet": "", "collected_at": "2026-08-11"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)

    result = graph_queries.policy_event_mention_impact("전세사기", before_days=7, after_days=7)

    assert result == {
        "found": True,
        "policy_event": {"title": "전세사기 특별법 시행령 개정", "announced_at": "2026-08-10"},
        "before_count": 1,
        "after_count": 2,
        "change": 1,
    }


def test_policy_event_mention_impact_no_alignment_counts_all_mentions(monkeypatch):
    monkeypatch.setattr(graph_queries, "_today", lambda: date(2026, 8, 21))
    events = [{"title": "국토부 인사 발령", "announced_at": "2026-08-15"}]
    mentions = [
        {"title": "전세 매물 정보", "snippet": "", "collected_at": "2026-08-12"},
        {"title": "미국 부동산 동향", "snippet": "", "collected_at": "2026-08-16"},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_policy_events_since", lambda days: events)
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)

    result = graph_queries.policy_event_mention_impact("인사", before_days=7, after_days=7)

    assert result["before_count"] == 1
    assert result["after_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph_queries.py -k policy_event_mention_impact -v`
Expected: FAIL with `AttributeError: module 'graph_queries' has no attribute 'policy_event_mention_impact'`

- [ ] **Step 3: Write the implementation**

`graph_queries.py`의 `category_alignment_counts` 함수 뒤에 추가:
```python
def policy_event_mention_impact(
    policy_keyword: str, before_days: int = 7, after_days: int = 7
) -> dict:
    """제목에 policy_keyword가 포함된 정책 발표를 찾아, 그 발표일 전/후 기간의 관련
    뉴스 언급 건수를 비교한다 — "이 정책 발표 전후로 관련 브랜드 뉴스가 늘었어?" 같은
    질문에 쓴다. 최근 365일 내에서 가장 최근에 매칭되는 발표 하나를 기준으로 삼는다.

    Args:
        policy_keyword: 정책 발표 제목에서 찾을 키워드(예: "전세사기 특별법").
        before_days: 발표일 이전 며칠을 "전" 기간으로 볼지 (기본 7일).
        after_days: 발표일 이후 며칠을 "후" 기간으로 볼지 (기본 7일).

    Returns:
        매칭되는 발표가 없으면 {"found": False, "policy_keyword": str}. 있으면
        {"found": True, "policy_event": {"title": str, "announced_at": str},
        "before_count": int, "after_count": int, "change": int} — change는
        after_count - before_count. 발표의 카테고리와 대응되는 뉴스카테고리가 온톨로지에
        없으면 카테고리로 거르지 않고 기간 내 전체 언급을 집계한다.
    """
    events = cached_db.get_policy_events_since(365)
    matches = [e for e in events if policy_keyword in e.get("title", "")]
    if not matches:
        return {"found": False, "policy_keyword": policy_keyword}

    event = max(matches, key=lambda e: e.get("announced_at") or "")
    announced_str = (event.get("announced_at") or "")[:10]
    if not announced_str:
        return {"found": False, "policy_keyword": policy_keyword}
    announced_date = datetime.strptime(announced_str, "%Y-%m-%d").date()

    related_news_categories: set[str] = set()
    for category in policy_feed.categorize(event.get("title", "")):
        related_news_categories.update(ontology.aligned_news_categories(category))

    fetch_days = max((_today() - announced_date).days + after_days, before_days) + 1
    mentions = cached_db.get_mentions_since(fetch_days)

    before_start = (announced_date - timedelta(days=before_days)).isoformat()
    announced_iso = announced_date.isoformat()
    after_end = (announced_date + timedelta(days=after_days)).isoformat()

    before_count = 0
    after_count = 0
    for m in mentions:
        m_date = (m.get("collected_at") or "")[:10]
        if not m_date:
            continue
        if related_news_categories:
            text = f"{m.get('title', '')} {m.get('snippet', '')}"
            if not related_news_categories & set(news_feed.categorize(text)):
                continue
        if before_start <= m_date < announced_iso:
            before_count += 1
        elif announced_iso <= m_date <= after_end:
            after_count += 1

    return {
        "found": True,
        "policy_event": {"title": event.get("title", ""), "announced_at": announced_str},
        "before_count": before_count,
        "after_count": after_count,
        "change": after_count - before_count,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph_queries.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add graph_queries.py tests/test_graph_queries.py
git commit -m "feat: 정책 발표 전후 뉴스 변화 조회 도구(policy_event_mention_impact) 추가"
```

---

### Task 4: `graph_queries.py` — `brand_role_category_breakdown`

**Files:**
- Modify: `graph_queries.py` (함수 추가, `utils` import는 이미 Task 2에서 추가됨)
- Test: `tests/test_graph_queries.py` (추가)

**Interfaces:**
- Consumes: 기존 `utils.load_keywords() -> dict`(`{"brands": [{"name": str, "role": str}, ...], ...}`), `cached_db.get_mentions_since`, `news_feed.categorize`.
- Produces: `graph_queries.brand_role_category_breakdown(days: int = 30) -> dict`.

- [ ] **Step 1: Write the failing test**

`tests/test_graph_queries.py`에 추가:
```python
def test_brand_role_category_breakdown(monkeypatch):
    monkeypatch.setattr(
        graph_queries.utils,
        "load_keywords",
        lambda: {
            "brands": [
                {"name": "프롭티어", "role": "own"},
                {"name": "직방", "role": "competitor"},
            ]
        },
    )
    mentions = [
        {"brand": "프롭티어", "title": "프롭티어 AI 신규 도입", "snippet": ""},
        {"brand": "직방", "title": "직방 전세 매물 확대", "snippet": ""},
        {"brand": "알수없는브랜드", "title": "매물 정보", "snippet": ""},
    ]
    monkeypatch.setattr(graph_queries.cached_db, "get_mentions_since", lambda days: mentions)

    result = graph_queries.brand_role_category_breakdown(days=30)

    assert result == {
        "own": {"신규 도입": 1, "AI": 1},
        "competitor": {"매물": 1},
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph_queries.py -k brand_role_category_breakdown -v`
Expected: FAIL with `AttributeError: module 'graph_queries' has no attribute 'brand_role_category_breakdown'`

- [ ] **Step 3: Write the implementation**

`graph_queries.py`의 `policy_event_mention_impact` 함수 뒤에 추가:
```python
def brand_role_category_breakdown(days: int = 30) -> dict:
    """최근 N일간 언급을 브랜드 role(own/competitor/market, keywords.json 기준) ×
    뉴스카테고리로 교차집계한다 — "경쟁사들이 어느 카테고리에서 우리보다 많이
    언급돼?" 같은 질문에 쓴다.

    Args:
        days: 최근 며칠간을 볼지 (기본 30일).

    Returns:
        role을 키로, {카테고리명: 건수} 딕셔너리를 값으로 갖는 딕셔너리. 한 기사가
        여러 카테고리에 동시에 해당할 수 있어 role별 합계가 전체 언급 건수보다 클 수
        있다. keywords.json에 등록되지 않은 브랜드의 언급은 집계에서 제외된다.
    """
    brands = utils.load_keywords().get("brands", [])
    role_by_brand = {b["name"]: b.get("role", "market") for b in brands}
    mentions = cached_db.get_mentions_since(days)
    result: dict[str, dict[str, int]] = {}
    for m in mentions:
        role = role_by_brand.get(m.get("brand", ""))
        if not role:
            continue
        text = f"{m.get('title', '')} {m.get('snippet', '')}"
        bucket = result.setdefault(role, {})
        for category in news_feed.categorize(text):
            bucket[category] = bucket.get(category, 0) + 1
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph_queries.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add graph_queries.py tests/test_graph_queries.py
git commit -m "feat: 브랜드 role x 카테고리 교차집계 도구(brand_role_category_breakdown) 추가"
```

---

### Task 5: `agent_chat.py` — `_STATS_TOOLS`에 3개 도구 등록

**Files:**
- Modify: `agent_chat.py:22-27` (import 블록), `agent_chat.py:545-551` (`_STATS_TOOLS` 리스트)
- Test: `tests/test_agent_chat.py` (추가)

**Interfaces:**
- Consumes: Task 2/3/4의 `graph_queries.category_alignment_counts`, `graph_queries.policy_event_mention_impact`, `graph_queries.brand_role_category_breakdown`.
- Produces: 없음(등록이 끝. 이 도구들은 이제 Gemini automatic function calling으로 호출 가능).

- [ ] **Step 1: Write the failing test**

`tests/test_agent_chat.py`에 추가:
```python
def test_stats_tools_include_graph_queries_tools():
    import graph_queries

    assert graph_queries.category_alignment_counts in agent_chat._STATS_TOOLS
    assert graph_queries.policy_event_mention_impact in agent_chat._STATS_TOOLS
    assert graph_queries.brand_role_category_breakdown in agent_chat._STATS_TOOLS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_chat.py -k graph_queries_tools -v`
Expected: FAIL with `AssertionError` (아직 `_STATS_TOOLS`에 없음)

- [ ] **Step 3: Write the implementation**

`agent_chat.py:22-27`의 import 블록을 다음으로 교체(`graph_queries` 한 줄 추가, 나머지는 그대로):
```python
import cached_db
import db
import graph_queries
import news_feed
import policy_feed
import summarizer
import utils
```

`agent_chat.py:545-551`의 `_STATS_TOOLS` 리스트를 다음으로 교체(마지막에 3줄 추가, 기존 항목은 그대로):
```python
_STATS_TOOLS = [
    get_channel_counts, get_overview_stats, get_brand_mention_count, get_policy_source_counts,
    get_briefing_highlights, get_collection_health, compare_brand_mentions, get_vectorization_status,
    get_top_mentioned_brands, get_news_category_counts, get_policy_category_counts,
    compare_collection_periods, get_api_cost_summary, get_tracked_brands, get_pdf_report_stats,
    get_top_viewed_policy_events, search_mentions, get_brand_mention_trend, get_trending_brands,
    graph_queries.category_alignment_counts, graph_queries.policy_event_mention_impact,
    graph_queries.brand_role_category_breakdown,
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent_chat.py tests/test_graph_queries.py tests/test_ontology.py -v`
Expected: 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add agent_chat.py tests/test_agent_chat.py
git commit -m "feat: 온톨로지 기반 그래프 쿼리 도구 3종을 AI AGENT에 연동"
```

---

## Final Check

전체 테스트 스위트가 깨지지 않았는지 마지막에 한 번 더 확인:

Run: `pytest -q`
Expected: 기존 테스트 전부 PASS + 이번에 추가한 테스트(ontology 4개, graph_queries 9개, agent_chat 1개) PASS.
