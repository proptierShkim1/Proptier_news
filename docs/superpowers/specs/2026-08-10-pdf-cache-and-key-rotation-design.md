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
- 모듈 전역에 캐시 슬롯 하나만 둔다: `_cache: tuple[str, bytes] | None` (키와 바이트를
  한 튜플로 묶어 한 번에 대입한다 — 아래 "왜 락이 필요한가" 참고).
- **캐시 키는 손으로 고른 필드 목록이 아니라 실제로 렌더링되는 HTML의 해시다**:
  `hashlib.sha256(build_deck_html(items, total_count, ai_count).encode()).hexdigest()`.
  최초 구현은 `(mention_id, bool(summary))` + `total_count`/`ai_count`처럼 "PDF에 영향을
  주는 필드"를 손으로 골라 키를 만들었는데, 이 방식은 표지의 날짜 줄(`datetime.now()`
  기준)과 카드별 최근성 문구(`news_feed.build_news_items()`가 12시간 컷오프로 매기는
  "최근 12시간 내 수집되어 신선도가 높습니다" vs "누적 수집 데이터 중 상위 신호로
  선정되었습니다")를 캐치하지 못했다 — 둘 다 렌더링 결과에 영향을 주지만 손으로 고른
  필드 목록에는 없어서, items/total_count/ai_count가 완전히 같아도 캐시가 어제 날짜나
  stale한 문구를 그대로 돌려줄 수 있었다. 렌더러가 실제로 만든 HTML을 해시하면 렌더러가
  읽는 모든 필드가 구조적으로 다 들어가므로 이런 drift가 원천적으로 불가능하다.
  `build_deck_html`은 5개 항목에 대한 순수 문자열 포매팅이라 매 호출마다 다시 계산해도
  비용은 무시할 수준— 비싼 부분은 Chromium 렌더링(`generate_pdf_bytes`)뿐이다.
- 새 함수 `get_or_generate_pdf_bytes(items, total_count=0, ai_count=0) -> bytes`:
  키가 이전과 같고 캐시된 바이트가 있으면 그대로 반환, 다르면 `generate_pdf_bytes()`를
  호출해 결과를 캐시에 저장한 뒤 반환.
- `views/report.py`의 "PDF 생성" 버튼 핸들러가 `generate_pdf_bytes` 대신
  `get_or_generate_pdf_bytes`를 호출하도록 한 줄 교체. 그 외 로직(스피너, 에러 처리,
  세션 상태 저장)은 변경 없음.
- 명시적 invalidation 호출은 어디에도 추가하지 않는다 — `cached_db`가 60초 TTL로 이미
  새 수집 데이터를 반영하므로, 새 데이터가 top5/total_count/ai_count를 바꾸면 렌더링된
  HTML이 자연히 달라져 캐시 키도 달라져 재생성된다. `collector.py`/`scheduler.py`에
  캐시 지식을 결합시키지 않는 기존 원칙(2026-08-06 성능 개선 때 정한 것)과 일치.
- **module-level `threading.Lock()`으로 single-flight 처리한다** — 최초 설계는 "락
  없음: 동시 캐시미스 시 드물게 중복 생성될 수 있으나 입력이 같으므로 결과도 같아
  무해하다"고 판단해 범위 밖으로 뒀는데, 이 판단은 캐시 상태를 `_cache_key`/
  `_cache_bytes` 두 개의 별도 전역 변수로 나눠 쓰던 구현의 버그를 놓치고 있었다: 두
  스레드가 서로 *다른* 키로 동시에 캐시미스를 내면(예: 하나는 새 수집 데이터가 반영된
  요청, 하나는 그 직전 데이터로 이미 진행 중이던 요청) `_cache_key = key`와
  `_cache_bytes = pdf_bytes`라는 두 번의 대입이 인터리빙될 수 있어 캐시가
  `(key_B, bytes_A)`처럼 서로 안 맞는 조합으로 굳어버릴 수 있었다 — 이후 요청은 이
  틀린 조합이 데이터가 다시 바뀔 때까지 계속 캐시 히트로 서빙된다. "동시 캐시미스는
  입력이 같으니 무해하다"는 전제 자체가 "입력이 다를 수도 있다"는 경우를 놓친 것.
  이번 라운드에서 (a) 캐시 슬롯을 `_cache = (key, pdf_bytes)` 튜플 하나로 합쳐 한 번의
  대입으로 원자적으로 갈아치우게 하고, (b) 캐시미스 시 더블체크 락(double-checked
  locking)으로 콜드 캐시에 동시에 들어온 같은 키의 요청들이 Chromium을 한 번만 띄우고
  결과를 공유하게 했다. 덕분에 캐시 오염 경합이 사라지는 동시에, N명이 동시에 콜드
  캐시를 때려도 Chromium 프로세스가 N번 뜨는 낭비도 함께 없어졌다.

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
