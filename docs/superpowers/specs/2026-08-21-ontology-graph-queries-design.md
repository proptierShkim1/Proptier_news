# 온톨로지 + 그래프SQL 쿼리 도구 — 설계

## 배경
AI AGENT에는 이미 16개 지표 도구(`agent_chat._STATS_TOOLS`)와 벡터 검색(RAG)이 있지만,
서로 다른 분류 체계를 엮는 질문에는 답할 수 없다. 예: "이 정책 발표 전후로 관련 브랜드
뉴스가 늘었어?", "정책 카테고리별로 요즘 어떤 뉴스카테고리가 같이 뜨고 있어?" — 이런
질문은 `mentions`와 `policy_events`를 카테고리/날짜로 엮어야 답이 나오는데, 현재 코드
전체에 그 둘을 잇는 JOIN이 하나도 없다(`db.py`의 JOIN 2곳은 모두 벡터색인↔원본 테이블
자기참조일 뿐).

2026-08-18 브레인스토밍에서 "질문 100개당 함수 100개"가 아니라 **관계를 선언하고
범용 파라미터형 쿼리 도구로 조합 커버**하는 방향(B안)을 확정했다. 이번 라운드는 그 첫
구현 — 사용자가 "조금이라도 써보고" 감을 잡는 게 목적이라 작게 시작한다.

## 범위
- 다룬다: 뉴스카테고리 ↔ 정책카테고리 정렬 선언, 이를 이용한 그래프형 쿼리 도구 3개,
  AI AGENT 도구 등록.
- 다루지 않는다: DB 스키마 변경(카테고리를 컬럼으로 materialize하는 것), 실제 SQL
  `JOIN` 문법 사용, 브랜드-경쟁사 관계 재선언(이미 `keywords.json`에 있음), 랭그래프류
  오케스트레이션(2차 작업으로 분리돼 있음, [[project_ontology_graphsql_design_2026-08-18]]
  참고).

**왜 스키마를 안 건드리나:** `mentions`/`policy_events` 테이블엔 카테고리 컬럼이 없고,
`news_feed.categorize()`/`policy_feed.categorize()`가 제목/본문 텍스트를 키워드 매칭해
그때그때 계산한다. 이 프로젝트는 최근(8/14~19) 컬럼 매핑/백필 관련 DB 손상을 여러 번
겪었고, 사용자도 "기존 프로그램에 영향이 없는" 방식을 명시적으로 선택했다. 조인 대상
값이 원래 DB에 저장돼 있지 않으므로, SQL이 아니라 Python에서 계산 후 합치는 쪽이
정석에 가깝다(BI 시맨틱 레이어인 dbt/LookML/Cube.js도 관계 수가 적을 때 그래프 DB
없이 코드 선언 + 애플리케이션 레벨 조인을 쓴다).

## 구현 범위

### 1. `ontology.py` (신규 파일)
뉴스카테고리 8종(`news_feed.CATEGORY_ORDER`)과 정책카테고리 5종
(`policy_feed.POLICY_CATEGORY_ORDER`) 사이의 정적 대응 관계만 선언한다. 브랜드 role은
이미 `keywords.json`에 있으므로 재선언하지 않는다.

```python
CATEGORY_ALIGNMENT: dict[str, list[str]] = {
    "정책":     ["규제·법령", "지원·사업"],
    "매물":     ["지원·사업"],
    "시세·감정": ["통계·조사"],
}

def aligned_policy_categories(news_category: str) -> list[str]:
    """대응하는 정책카테고리가 없으면 빈 리스트."""

def aligned_news_categories(policy_category: str) -> list[str]:
    """CATEGORY_ALIGNMENT를 역방향으로 조회. 대응 없으면 빈 리스트."""
```
신규 도입/AI/부동산AI/해외/리포트는 정책카테고리와 자연스러운 대응이 없어 선언하지
않는다(억지로 다 엮지 않음).

### 2. `graph_queries.py` (신규 파일) — 도구 3개
기존 `agent_chat.get_news_category_counts`/`get_policy_category_counts`와 같은 패턴
(`cached_db`로 기간 내 원본을 가져와 `categorize()`로 즉석 분류)을 재사용한다.

- **`category_alignment_counts(news_category="", policy_category="", days=30) -> dict | list[dict]`**
  한쪽 카테고리명을 주면 온톨로지로 대응되는 반대쪽 카테고리들의 건수를 함께 반환:
  `{"news_category": "정책", "aligned_policy_categories": ["규제·법령", "지원·사업"],
  "news_count": int, "policy_counts": {"규제·법령": int, "지원·사업": int}, "days": int}`.
  둘 다 안 주면 `CATEGORY_ALIGNMENT`에 선언된 모든 짝을 이 형태의 리스트로 반환(포괄적
  질문용). 둘 다 주면 `news_category`를 우선한다(뒤에 준 `policy_category`는 무시).
  인식 못 하는 카테고리명이 들어오면 대응 리스트가 빈 채로 정상 반환(예외 아님).

- **`policy_event_mention_impact(policy_keyword, before_days=7, after_days=7) -> dict`**
  제목에 `policy_keyword`가 포함된 정책 발표 중 가장 최근 것을 찾아(최근 365일 범위),
  그 발표일 기준 전/후 기간의 관련 뉴스 언급 건수를 비교한다. 관련 뉴스는 그 발표의
  제목을 `policy_feed.categorize()`로 매겨(여러 개일 수 있음) 각각
  `aligned_news_categories()`로 뒤집어 얻은 뉴스카테고리들의 합집합으로 필터링한다.
  매칭되는 발표가 없으면
  `{"found": False, "policy_keyword": str}`. 있으면
  `{"found": True, "policy_event": {"title": str, "announced_at": str},
  "before_count": int, "after_count": int, "change": int}`.

- **`brand_role_category_breakdown(days=30) -> dict`**
  기간 내 언급을 브랜드 role(own/competitor/market, `keywords.json` 기준) × 뉴스카테고리로
  교차집계: `{"own": {"매물": int, ...}, "competitor": {...}, "market": {...}}`.

세 도구 모두 기존 `_STATS_TOOLS`처럼 try/except 없이 plain dict/list를 반환하고,
독스트링에 Args/Returns를 한국어로 구체적으로 적어 Gemini function calling 스키마로
그대로 쓴다.

### 3. `agent_chat.py` 연동
`graph_queries`의 세 함수를 import해서 `_STATS_TOOLS` 리스트에 추가. 그 외 도구 선택/
호출 로직은 기존 자동 함수 호출 흐름을 그대로 탄다(코드 변경 없음).

## 테스트
`tests/test_ontology.py`, `tests/test_graph_queries.py` 신설. 기존
`tests/test_agent_chat.py`의 컨벤션(실제 DB 대신 `cached_db.get_mentions_since`/
`get_policy_events_since`를 `monkeypatch`로 고정값 대체)을 그대로 따른다.
- `ontology.py`: 정방향/역방향 조회, 대응 없는 카테고리에 빈 리스트 반환.
- `category_alignment_counts`: 한쪽만 줄 때/둘 다 안 줄 때/모르는 카테고리명일 때 3가지
  케이스.
- `policy_event_mention_impact`: 매칭되는 발표 있음/없음, 전/후 건수 계산 정확성.
- `brand_role_category_breakdown`: role별 집계가 keywords.json 기준과 일치하는지.
- `agent_chat.py`: 세 함수가 `_STATS_TOOLS`에 등록돼 있는지 확인하는 테스트 1개 추가.

## 영향받지 않는 부분
- 기존 16개 지표 도구, 벡터 검색(RAG), 하이브리드 검색 — 변경 없음.
- `mentions`/`policy_events` 테이블 스키마 — 변경 없음.
- `news_feed.categorize`/`policy_feed.categorize`의 카테고리 판정 로직 자체 — 변경 없음,
  그대로 재사용만 함.
- 2차 작업(랭그래프 오케스트레이션)은 이번 스펙에 포함하지 않음.
