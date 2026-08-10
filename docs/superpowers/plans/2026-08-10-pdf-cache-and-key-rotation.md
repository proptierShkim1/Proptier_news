# PDF 캐시 + Gemini 키 로테이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 동시 접속자가 늘어도 (1) 동일한 PDF를 매번 Chromium으로 재생성하지 않고, (2) Gemini API 키 시도가 항상 같은 키부터 몰리지 않게 한다.

**Architecture:** `report_pdf.py`에 모듈 전역 단일 슬롯 캐시를 추가해 `views/report.py`가 이를 통해 PDF 바이트를 받아오게 하고, `summarizer.py`/`vectorizer.py`의 `_load_api_keys()`가 매 호출마다 키 순서를 섞어 반환하도록 바꾼다. 기존 함수 시그니처와 호출 계약은 유지한다.

**Tech Stack:** Python, pytest, `unittest.mock`.

## Global Constraints

- 캐시 키는 `generate_pdf_bytes(items, total_count, ai_count)`에 실제로 들어가는 입력값만 사용한다: 각 item의 `mention_id`와 `bool(item.get("summary"))`, 그리고 `total_count`, `ai_count`.
- 캐시에 락을 추가하지 않는다(설계 문서에서 합의됨 — 동시 캐시미스는 드물고 결과가 같아 무해).
- `collector.py`/`scheduler.py`에는 캐시 무효화 호출을 추가하지 않는다. 캐시는 순수하게 입력값 비교로만 갱신된다.
- 키 순서 셔플은 `_load_api_keys()` 내부에서만 하고, 호출부(`for key in keys`)는 수정하지 않는다.

---

### Task 1: `report_pdf.py`에 콘텐츠 기반 PDF 캐시 추가

**Files:**
- Modify: `report_pdf.py` (파일 끝, `generate_pdf_bytes` 함수 뒤에 추가)
- Test: `tests/test_report_pdf.py`

**Interfaces:**
- Consumes: 기존 `generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes` (수정하지 않음, 캐시 미스일 때 그대로 호출).
- Produces: `get_or_generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes` — Task 2에서 `views/report.py`가 이 함수를 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_report_pdf.py` 파일 끝에 추가:

```python
from unittest.mock import patch


def _item_with_id(mention_id, summary=""):
    item = _item("제목")
    item["mention_id"] = mention_id
    item["summary"] = summary
    return item


def test_get_or_generate_pdf_bytes_returns_cached_bytes_for_same_inputs():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", return_value=b"pdf-bytes") as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

    assert first == b"pdf-bytes"
    assert second == b"pdf-bytes"
    mock_gen.assert_called_once_with(items, 10, 2)


def test_get_or_generate_pdf_bytes_regenerates_when_items_change():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items_v1 = [_item_with_id(1, "")]
    items_v2 = [_item_with_id(1, "요약 생김")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items_v1, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items_v2, total_count=10, ai_count=2)

    assert first == b"v1"
    assert second == b"v2"
    assert mock_gen.call_count == 2


def test_get_or_generate_pdf_bytes_regenerates_when_total_count_changes():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        report_pdf.get_or_generate_pdf_bytes(items, total_count=11, ai_count=2)

    assert mock_gen.call_count == 2
```

파일 맨 위 import 문에 `import report_pdf`가 이미 있으므로 그대로 두고, `_item` 헬퍼(이미 파일에 있음)를 재사용한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_report_pdf.py -k get_or_generate -v`
Expected: FAIL — `AttributeError: module 'report_pdf' has no attribute 'get_or_generate_pdf_bytes'`

- [ ] **Step 3: 최소 구현 작성**

`report_pdf.py` 파일 끝(`generate_pdf_bytes` 함수 뒤)에 추가:

```python
_cache_key = None
_cache_bytes = None


def get_or_generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes:
    """generate_pdf_bytes()와 동일한 입력이면 마지막으로 만든 PDF 바이트를 그대로
    돌려주고, 입력이 달라졌을 때만 다시 렌더링한다. 동시 접속자가 같은 시점엔 동일한
    top5/집계를 보므로(이 페이지엔 사용자별 필터가 없음), 서버 프로세스 전체가 캐시
    슬롯 하나를 공유해도 안전하다."""
    global _cache_key, _cache_bytes

    key = (
        tuple((item.get("mention_id"), bool(item.get("summary"))) for item in items),
        total_count,
        ai_count,
    )
    if key == _cache_key and _cache_bytes is not None:
        return _cache_bytes

    pdf_bytes = generate_pdf_bytes(items, total_count, ai_count)
    _cache_key = key
    _cache_bytes = pdf_bytes
    return pdf_bytes
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_report_pdf.py -v`
Expected: PASS (기존 테스트 포함 전체)

- [ ] **Step 5: 커밋**

```bash
git add report_pdf.py tests/test_report_pdf.py
git commit -m "feat: PDF 생성에 콘텐츠 기반 캐시 추가"
```

---

### Task 2: `views/report.py`가 캐시 경유 함수를 쓰도록 교체

**Files:**
- Modify: `views/report.py:8` (import), `views/report.py:45` (호출부)
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: Task 1의 `report_pdf.get_or_generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes`.
- Produces: 없음(최종 사용자 코드 경로).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_report.py` 파일 끝에 추가:

```python
def test_report_view_wires_pdf_button_to_cache_aware_generator():
    from report_pdf import get_or_generate_pdf_bytes

    assert report.get_or_generate_pdf_bytes is get_or_generate_pdf_bytes
    assert not hasattr(report, "generate_pdf_bytes")
```

`render()` 전체를 mock으로 감싸는 대신, "이 모듈이 캐시 경유 함수를 가져와서 쓰고 있고 캐시 없는 원본 함수는 더 이상 직접 참조하지 않는다"는 wiring만 확인한다 — 실제 캐싱 동작 자체는 Task 1의 `test_report_pdf.py`가 이미 충분히 검증한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_report.py -k wires_pdf_button -v`
Expected: FAIL — `AttributeError: module 'views.report' has no attribute 'get_or_generate_pdf_bytes'`

- [ ] **Step 3: 최소 구현 작성**

`views/report.py:8`을 수정:

```python
from report_pdf import build_deck_html, generate_pdf_bytes, get_or_generate_pdf_bytes
```

`views/report.py:45`(현재 `generate_pdf_bytes(top5, total_count, ai_count)` 호출부)를 수정:

```python
                    st.session_state["report_pdf_bytes"] = get_or_generate_pdf_bytes(top5, total_count, ai_count)
```

`generate_pdf_bytes` import는 미리보기 섹션에서 쓰지 않으므로(미리보기는 `build_deck_html`만 씀) 그대로 두거나 제거해도 되지만, 다른 곳에서 참조하지 않는지 확인 후 필요 없으면 import에서 제거한다. 실제로 `views/report.py`에서 `generate_pdf_bytes`를 직접 호출하는 곳이 이 한 줄뿐이므로, import 목록에서 `generate_pdf_bytes`는 제거하고 `get_or_generate_pdf_bytes`만 남긴다:

```python
from report_pdf import build_deck_html, get_or_generate_pdf_bytes
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_report.py -v`
Expected: PASS (기존 테스트 포함 전체)

- [ ] **Step 5: 커밋**

```bash
git add views/report.py tests/test_report.py
git commit -m "feat: PDF 생성 버튼이 캐시 경유 함수를 쓰도록 교체"
```

---

### Task 3: `summarizer.py` — API 키 시도 순서 랜덤화

**Files:**
- Modify: `summarizer.py:1-23`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Consumes: 없음.
- Produces: `_load_api_keys() -> list[str]`(반환값 순서가 매 호출마다 달라질 수 있음 — 시그니처는 동일, 순서 보장만 사라짐).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summarizer.py` 파일 끝에 추가:

```python
def test_load_api_keys_returns_all_keys_regardless_of_order(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3")

    result = summarizer._load_api_keys()

    assert sorted(result) == ["key1", "key2", "key3"]


def test_load_api_keys_shuffles_order_across_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3,key4,key5,key6,key7,key8")

    orders = {tuple(summarizer._load_api_keys()) for _ in range(20)}

    assert len(orders) > 1
```

두 번째 테스트는 `random.shuffle`이 실제로 순서를 바꾸는지를 통계적으로 확인한다(8개 키를 20번 섞으면 매번 같은 순서가 나올 확률은 실질적으로 0이라 flake 걱정 없음).

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_summarizer.py -k shuffles_order -v`
Expected: FAIL — `assert len(orders) > 1`이 `assert 1 > 1`로 실패(항상 같은 순서).

- [ ] **Step 3: 최소 구현 작성**

`summarizer.py` 상단 import에 `import random` 추가(9번째 줄, `import os` 다음):

```python
import os
import random
from pathlib import Path
```

`_load_api_keys()`(21-23번째 줄)를 수정:

```python
def _load_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    random.shuffle(keys)
    return keys
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS (기존 failover 테스트 포함 전체 — `test_summarize_article_tries_next_key_on_failure`는 `genai.Client`의 `side_effect`가 호출 순서로 매핑되어 키 문자열과 무관하므로 셔플 후에도 그대로 통과함)

- [ ] **Step 5: 커밋**

```bash
git add summarizer.py tests/test_summarizer.py
git commit -m "feat: Gemini API 키 시도 순서를 매 호출마다 랜덤화"
```

---

### Task 4: `vectorizer.py` — API 키 시도 순서 랜덤화

**Files:**
- Modify: `vectorizer.py:1-31`
- Test: `tests/test_vectorizer.py`

**Interfaces:**
- Consumes: 없음.
- Produces: `_load_api_keys() -> list[str]`(Task 3과 동일한 계약 — 순서만 매 호출마다 랜덤).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_vectorizer.py` 파일 끝에 추가:

```python
def test_load_api_keys_returns_all_keys_regardless_of_order(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3")

    result = vectorizer._load_api_keys()

    assert sorted(result) == ["key1", "key2", "key3"]


def test_load_api_keys_shuffles_order_across_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3,key4,key5,key6,key7,key8")

    orders = {tuple(vectorizer._load_api_keys()) for _ in range(20)}

    assert len(orders) > 1
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_vectorizer.py -k shuffles_order -v`
Expected: FAIL — `assert len(orders) > 1`이 `assert 1 > 1`로 실패.

- [ ] **Step 3: 최소 구현 작성**

`vectorizer.py` 상단 import에 `import random` 추가(11번째 줄, `import json` 다음):

```python
import json
import os
import random
import threading
import uuid
```

`_load_api_keys()`(29-31번째 줄)를 수정:

```python
def _load_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    random.shuffle(keys)
    return keys
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_vectorizer.py -v`
Expected: PASS (기존 failover 테스트 포함 전체)

- [ ] **Step 5: 커밋**

```bash
git add vectorizer.py tests/test_vectorizer.py
git commit -m "feat: 벡터화 임베딩 호출의 API 키 시도 순서를 매 호출마다 랜덤화"
```

---

### Task 5: 전체 테스트 스위트 확인

**Files:** 없음(검증 전용).

**Interfaces:** 없음.

- [ ] **Step 1: 전체 테스트 실행**

Run: `pytest -v`
Expected: PASS — Task 1~4에서 건드린 파일 외에 회귀가 없는지 전체 스위트로 확인(특히 `tests/test_report.py`, `tests/test_report_pdf.py`, `tests/test_summarizer.py`, `tests/test_vectorizer.py`, `tests/test_agent_chat.py`).

- [ ] **Step 2: 실패가 있으면 원인 파악 후 수정, 없으면 완료**

실패하는 테스트가 있다면 어떤 Task의 변경과 충돌하는지 확인해 그 Task 커밋 위에 새 커밋으로 수정한다(기존 커밋을 amend하지 않음).
