# PDF 캐시 + Gemini 키 로테이션 — 설계

## 배경
"50명이 동시에 쓴다면"을 가정해 점검하다 두 지점을 확인했다.

1. `views/report.py`의 PDF 생성이 요청마다 `report_pdf.generate_pdf_bytes()`로
   Playwright Chromium을 새로 띄운다. 이 페이지엔 날짜/채널 필터 UI가 없어 모든 사용자가
   같은 시점엔 동일한 `enabled_channels` 기준 top5를 보므로, 동시에 여러 명이 누르면
   똑같은 내용을 위해 크로미움을 중복으로 띄우는 낭비가 생긴다.
2. `summarizer.py`/`vectorizer.py`의 `_load_api_keys()`가 `GEMINI_API_KEYS`를 항상 같은
   순서로 반환하고, 호출부는 `for key in keys`로 앞에서부터 순서대로 시도(실패 시에만
   다음 키로 failover)한다. 동시 요청이 몰리면 다들 1번 키부터 두드려 그 키의 분당
   한도에 먼저 걸리고 나서야 순차로 다음 키로 넘어가는 지연이 쌓인다.

## 범위
이번 라운드는 이 두 지점만 다룬다. 서버 하드웨어 증설, PDF 페이지에 필터 UI를 추가하는
것, 키별 사용량 모니터링 등은 범위 밖이다.

## 구현 범위

### 1. `report_pdf.py` — 콘텐츠 기반 PDF 캐시
- 모듈 전역에 캐시 슬롯 하나만 둔다: `_cache_key: tuple | None`, `_cache_bytes: bytes | None`
  (락 없음 — 동시 캐시미스 시 드물게 중복 생성될 수 있으나 입력이 같으므로 결과도 같아
  무해하다고 판단, 범위 밖으로 둠).
- 캐시 키는 `generate_pdf_bytes()`에 실제로 들어가는 입력만으로 만든다:
  `tuple((item["mention_id"], bool(item.get("summary"))) for item in items) + (total_count, ai_count)`.
- 새 함수 `get_or_generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes`:
  키가 이전과 같고 캐시된 바이트가 있으면 그대로 반환, 다르면 `generate_pdf_bytes()`를
  호출해 결과를 캐시에 저장한 뒤 반환.
- `views/report.py`의 "PDF 생성" 버튼 핸들러가 `generate_pdf_bytes` 대신
  `get_or_generate_pdf_bytes`를 호출하도록 한 줄 교체. 그 외 로직(스피너, 에러 처리,
  세션 상태 저장)은 변경 없음.
- 명시적 invalidation 호출은 어디에도 추가하지 않는다 — `cached_db`가 60초 TTL로 이미
  새 수집 데이터를 반영하므로, 새 데이터가 top5/total_count/ai_count를 바꾸면 캐시 키가
  자연히 달라져 재생성된다. `collector.py`/`scheduler.py`에 캐시 지식을 결합시키지 않는
  기존 원칙(2026-08-06 성능 개선 때 정한 것)과 일치.

### 2. `summarizer.py` / `vectorizer.py` — 키 순서 랜덤화
- 두 파일의 `_load_api_keys()`를 리스트 생성 후 `random.shuffle()`로 섞어서 반환하도록
  수정(`import random` 추가). 호출부(`for key in keys`)는 변경 없음 — 매 호출마다 시도
  순서만 랜덤해진다.
- `has_api_keys()`처럼 순서가 의미 없는 호출부에는 영향 없음.

## 테스트
- `report_pdf.py`: `generate_pdf_bytes`를 mock해서 (a) 같은 items/total_count/ai_count로
  두 번 호출하면 mock이 한 번만 호출됨, (b) items가 달라지면(예: mention_id 또는 summary
  존재 여부 변경) 다시 호출됨을 확인.
- `summarizer.py`/`vectorizer.py`: 기존 `test_summarize_article_tries_next_key_on_failure`
  류 테스트는 `genai.Client`의 `side_effect`가 호출 순서(실패→성공)로 매핑되어 키 문자열
  자체와 무관하므로 셔플 후에도 그대로 통과함을 확인. 별도로 `random.shuffle`이 호출됨을
  확인하는 테스트는 추가하지 않음(구현 세부사항이라 과한 결합).

## 영향받지 않는 부분
- `cached_db.py`의 60초 TTL 쿼리 캐시, DB WAL 모드, 활동 로그— 변경 없음.
- PDF의 콘텐츠(카드 레이아웃, AI 요약 로직)는 그대로, 캐싱 레이어만 앞에 추가.
- 벡터 검색(`search_similar_mentions`/`search_similar_policy_events`)의 결과 자체는
  키 선택과 무관하므로 동일.
