# 네이버뉴스 API 수집 — 설계

## 배경
현재 "신규 게시물" 수집은 네이버(블로그/카페)·구글(뉴스 RSS)·다음(뉴스)·커뮤니티(디시인사이드)
4채널을 모두 HTML/RSS 스크래핑으로 가져온다. API 키 없이 동작하는 장점이 있지만, 대상
사이트가 마크업을 바꾸면 깨질 수 있다. 이번 작업은 네이버 공식 뉴스 검색 API(Client
ID/Secret 필요)를 새 수집 채널로 추가한다.

기존 4채널과 성격이 다른 완전히 독립된 수집 흐름으로 둔다 — UI 탭, 자동 스케줄, 실행
상태(락)를 모두 분리한다. 단, 나중에 데이터를 합치거나 조인할 가능성을 열어두기 위해
저장 스키마는 기존 `mentions`/`run_logs` 테이블을 그대로 재사용한다(새 테이블을 만들지
않음). 키워드도 별도로 관리하지 않고 기존 "키워드 관리"의 보유·경쟁사·시장 키워드를
그대로 검색어로 사용한다.

## 범위
네이버 뉴스 검색 API 1개 채널만 이번 라운드에 포함한다. 본문(전문) 스크래핑은 하지
않고, API가 제공하는 요약(`description`)만 저장한다.

## 구현 범위

### 1. `crawlers/naver_news_api.py` (신규)
- `search(term: str) -> list[dict]`: `GET https://openapi.naver.com/v1/search/news.json`
  호출, 파라미터 `query=term`, `display=100`, `sort="date"`.
- 인증 헤더 `X-Naver-Client-Id` / `X-Naver-Client-Secret`은 **함수 호출 시점에**
  `os.getenv("NAVER_CLIENT_ID")` / `os.getenv("NAVER_CLIENT_SECRET")`로 읽는다(모듈
  최상단에서 읽지 않음 — `views/settings.py`의 `load_dotenv()` 호출보다 `collector.py`
  import가 먼저 일어나는 현재 순서와 무관하게 항상 최신 값을 읽기 위함). 값이 비어 있으면
  `RuntimeError`를 던진다.
- 응답 `items[]`의 `title`/`description`에 포함된 `<b>` 태그를 정규식으로 제거한다.
- 반환 레코드는 기존 크롤러와 동일한 필드 계약을 따른다:
  `{"source_detail": "뉴스", "title": ..., "url": (originallink 있으면 그것, 없으면
  link), "snippet": description, "posted_at": pubDate를 "YYYY.MM.DD"로 변환}`.
- `fetch_content`는 만들지 않는다(본문 스크래핑 범위 밖).
- API 오류(4xx/5xx) 시 `requests`의 `raise_for_status()`가 예외를 던지도록 두고, 상위
  `_collect_one`의 기존 try/except가 흡수해 run_logs에 실패로 기록되게 한다(다른
  크롤러와 동일한 안전 계약).

### 2. `collector.py` — 독립 실행 함수 추가
- `_NAVER_NEWS_CHANNEL = "네이버뉴스"` 상수로 채널명을 고정(기존 `"네이버"`와 다른 값이라
  `mentions.channel`에서 충돌 없이 구분됨).
- `run_naver_news_collection(trigger="수동", on_progress=None, run_id=None) -> list[dict]`:
  `load_keywords()`로 브랜드 목록을 읽어, 기존 `_collect_one(brand_entry, "네이버뉴스",
  naver_news_api_crawler.search, trigger, run_id, context_words, exclude_terms)`를
  그대로 재사용해 브랜드별로 수집. `_CONTENT_FETCHERS`에는 이 채널을 등록하지 않는다.
- 브랜드 수집(`_state_lock`/`_active_run_id`)·정책 수집(`_policy_state_lock`/
  `_active_policy_run_id`)과 완전히 독립된 3번째 상태 관리:
  `_naver_news_state_lock`, `_active_naver_news_run_id` +
  `active_naver_news_run_id()` / `start_background_naver_news_collection(trigger="수동")
  -> str | None` (데몬 스레드, 중복 실행 방지는 기존 두 패턴과 동일).

### 3. `db.py` — 스키마 변경 없음, 조회 필터만 추가
- 테이블은 그대로 `mentions`/`run_logs` 재사용(신규 테이블 없음).
- `get_run_batches(limit: int = 50, channels: list[str] | None = None) -> list[dict]`:
  `channels`가 주어지면 SQL `WHERE channel IN (...)`로 걸러 그룹핑한다. 기본값 `None`은
  현재와 동일(필터 없음).
  - "신규 게시물" 탭 호출: `db.get_run_batches(limit=50, channels=["네이버", "구글",
    "다음", "커뮤니티"])` — 네이버뉴스 이력이 기존 이력 표에 섞여 나오지 않도록.
  - "네이버뉴스 API" 탭 호출: `db.get_run_batches(limit=50, channels=["네이버뉴스"])`.

### 4. `utils.py` / `scheduler.py` — 네이버뉴스 전용 자동 스케줄
- `utils.py`: `NAVER_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR /
  "naver_news_collection_schedule.json"` + `load_naver_news_collection_schedule()` /
  `save_naver_news_collection_schedule(cfg)` (기존 `_normalize_schedule_times` 재사용).
- `scheduler.py`: `_tick_new_posts()`/`_tick_policy()`와 독립된 `_tick_naver_news()` 추가
  (자체 `_last_fired_naver_news` 락 상태), `_tick()`에서 3개 틱을 모두 호출. 자동 실행 시
  `collector.run_naver_news_collection(trigger="자동")` 호출.
- 최초 실행 시 스케줄 파일이 없으면 빈 스케줄(`{"times": []}`)로 시작한다(정책 수집과
  달리 기본 시각을 미리 채우지 않음 — API 키 설정 전 자동 호출로 에러 로그만 쌓이는 것을
  방지).

### 5. `views/settings.py` — UI
`_render_data_collection()`의 서브탭을 3개로 확장:
`st.tabs(["📰 신규 게시물", "📡 네이버뉴스 API", "🏛️ 정부 정책"])`.

**신규 `_render_naver_news_collection_tab()`** (정책 서브탭과 동일한 위젯 패턴, key
접두어 `naver_news_`로 구분):
- 캡션: "네이버 공식 뉴스 검색 API로 수집합니다. 키워드 관리의 키워드를 그대로
  사용하며, 신규 게시물과 별도의 독립된 스케줄을 가집니다."
- `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`이 `.env`에 없으면 `st.warning`으로 안내만
  표시(입력 UI는 만들지 않음 — 배포 자격증명과 동일하게 `.env` 전용).
- 수집 시각 설정 UI(브랜드/정책과 동일 위젯 패턴).
- "🔄 지금 수집" 버튼(`type="primary"`) + 진행 상황 표시(기존
  `_show_collection_progress` 패턴 재사용 가능하면 재사용, 아니면 동일 패턴으로 신설).
- 수집 이력: `db.get_run_batches(limit=50, channels=["네이버뉴스"])` 표로 표시.

**`_render_brand_lookup_tab()` 수정:**
- 채널 드롭다운 `channels = ["전체", "네이버", "구글", "다음", "커뮤니티"]`에
  `"네이버뉴스"` 추가. 그 외 로직(페이지네이션/삭제/상세보기)은 채널 값에 무관하게 이미
  동작하므로 변경 없음.

### 6. `.env` — 자격증명
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 두 값을 추가(네이버 개발자센터에서 발급).
  UI로 입력받지 않고 배포 자격증명(`DEPLOY_*`)과 동일하게 `.env` 전용으로 관리한다.

## 범위 밖
- 기사 본문(전문) 스크래핑 — API가 요약만 제공하므로 이번 라운드는 요약만 저장. 필요해지면
  `originallink` 기반 사이트별 스크래핑을 별도 라운드로 추가.
- 네이버뉴스 채널과 기존 4채널 데이터를 실제로 합쳐서 보여주는 통합 뷰/분석 — 이번
  라운드는 스키마 호환성만 확보하고, 통합은 필요해지면 별도 라운드.
- 다른 네이버 공식 API(블로그/카페 검색 API로 기존 스크래퍼 대체) — 범위 밖.

## 테스트 계획
- `crawlers/naver_news_api.py`: 고정 JSON fixture로 `search()`가 필드를 정확히
  추출/변환하는지(`<b>` 태그 제거, `originallink` 우선 사용, pubDate 변환), 클라이언트
  ID/Secret이 없을 때 `RuntimeError`를 던지는지, API 오류 응답 시 예외가 전파되는지.
- `collector.py`: `run_naver_news_collection`이 채널을 `"네이버뉴스"`로 저장하는지,
  기존 4채널 수집과 독립된 락(동시 시작 시 하나는 `None` 반환)을 갖는지.
- `db.py`: `get_run_batches(channels=...)` 필터가 지정한 채널 조합만 포함된 배치를
  반환하는지(다른 채널이 섞인 배치는 제외).
- `scheduler.py`: `_tick_naver_news()`가 등록된 시각에만 1회 발화하고, 다른 두 틱과
  독립적으로 동작하는지(기존 `_tick_policy()` 테스트와 동일 패턴).
- `views/settings.py`: 네이버뉴스 API 서브탭에 수집 버튼이 있고 클릭 시 요약이
  표시되는지, 데이터 관리 채널 필터에 "네이버뉴스"가 추가되어 있는지.
