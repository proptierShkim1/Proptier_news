# 정부 정책 데이터 수집 — 설계

## 배경
현재 hana_p는 브랜드×채널(네이버/구글/다음/커뮤니티(디시인사이드)) 검색 결과만 수집한다.
자매 프로젝트 `MarketInsight`에는 이미 검증된 "정부 정책(공공기관 보도자료)" 수집 기능이
있으며, 이번 작업은 그 기능을 hana_p 구조에 맞춰 그대로 이식하는 것이다. 새로운 설계를
하는 대신 MarketInsight의 구현을 원본으로 삼아 포팅한다.

정책 데이터는 브랜드/채널 개념이 없다 — 기존 "신규 게시물"과 표 양식을 억지로 맞추지
않고, 정책 데이터에 맞는 자체 컬럼(등록일/분류/제목/조회수/보기)으로 별도 구성한다.

## 범위
국토교통부·한국부동산원·LH·서울시(정보소통광장)·HF·HUG·SH 7개 소스 전체를 이번 라운드에
포함한다. 자동 스케줄러도 브랜드 수집과 동일한 패턴(정책 전용 시각 설정)으로 처음부터
포함한다.

## 구현 범위

### 1. `db.py` — `policy_events` / `policy_run_logs` 테이블
```sql
CREATE TABLE IF NOT EXISTS policy_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,              -- 예: "국토부"
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    department   TEXT NOT NULL DEFAULT '',   -- 예: "주택토지"
    announced_at TEXT NOT NULL DEFAULT '',   -- "YYYY-MM-DD"
    view_count   INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL
);

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
```
- `insert_policy_event(record: dict) -> bool` — `mentions`의 `insert_mention`과 동일 계약
  (URL 중복이면 False, 신규면 True, `INSERT OR IGNORE` 활용).
- `get_policy_events(department: str = "") -> list[dict]` — `department` 필터, 최신
  `announced_at` 우선 정렬.
- `delete_policy_events(ids: list[int]) -> int`, `delete_all_policy_events() -> int` —
  `mentions`의 동명 함수와 동일 계약. **`policy_events` 테이블만 건드리며 `mentions`와는
  완전히 분리된 별도 테이블/함수**이므로, 정책 탭의 삭제 버튼이 실수로 브랜드 수집 데이터를
  지울 위험이 없다.
- `insert_policy_run_log`, `get_policy_run_logs`, `get_policy_run_batches` — run_id로
  묶어 배치 단위 이력 반환 (신설 테이블이라 run_logs처럼 레거시 시간-간격 추정 로직 불필요,
  처음부터 run_id 필수 컬럼).
- `init_db()`에 두 테이블 생성 호출 추가.

### 2. `crawlers/` — 신규 크롤러 7개
MarketInsight의 `crawlers/{molit,reb,lh,seoul_opengov,hf,hug,sh}.py`를 그대로 복사한다
(모듈 docstring의 프로젝트명만 "MarketInsight" → "hana_p"로 수정). 각 모듈은
`fetch_press_releases(start: date, end: date) -> list[dict]` 하나만 노출하며, 반환값은
`{"title", "url", "department", "announced_at", "view_count"}` 딕셔너리 리스트. 네트워크
오류/구조 변경 시 예외를 잡아 빈 리스트를 반환한다(기존 크롤러들과 동일한 안전 계약).
신규 pip 의존성 없음(requests/beautifulsoup4는 이미 사용 중).

### 3. `collector.py` — 정책 수집 실행 함수 추가
- `_collect_press_releases(fetch_press_releases, source, days, trigger, run_id) -> dict`:
  공통 fetch→source 태깅→저장→이력 기록 로직. 개별 소스 실패가 예외를 전파하지 않는다.
- `collect_molit_press_releases` / `collect_reb_press_releases` / `collect_lh_press_releases`
  / `collect_seoul_opengov_press_releases` / `collect_hf_press_releases` /
  `collect_hug_press_releases` / `collect_sh_press_releases` — 각각 `days: int = 30` 받아
  최근 N일치 수집.
- `collect_all_policy_events(days=30, on_progress=None, trigger="수동", run_id=None) -> dict`:
  7개 소스를 순서대로 모두 수집, 소스별 실패가 다른 소스를 막지 않음, 같은 run_id로 묶임.
- 브랜드 수집과 완전히 독립된 상태 관리: `_policy_state_lock`, `_active_policy_run_id`,
  `_policy_progress` + `active_policy_run_id()` / `get_policy_progress(run_id)` /
  `start_background_policy_collection(days=30, trigger="수동") -> str | None` (데몬 스레드,
  중복 실행 방지는 브랜드 수집과 동일 패턴).

### 4. `utils.py` / `scheduler.py` — 정책 전용 자동 스케줄
- `utils.py`: `POLICY_COLLECTION_SCHEDULE_FILE = DATA_DIR / "policy_collection_schedule.json"`
  + `load_policy_collection_schedule()` / `save_policy_collection_schedule(cfg)` (브랜드용과
  동일한 `_normalize_schedule_times` 재사용).
- `scheduler.py`: 브랜드용 `_tick()`과 독립된 `_tick_policy()` 추가 (자체 `_last_fired_policy`
  락 상태), `_loop()`에서 매 반복 두 틱을 모두 호출. 정책 수집 자동 실행 시
  `collector.collect_all_policy_events(days=30, trigger="자동")` 호출.
- 기본 스케줄 값: `09:00/10:00/11:00/13:00/14:00/15:00/16:00/17:00` (최초 실행 시
  `data/policy_collection_schedule.json`이 없으면 이 기본값으로 생성).

### 5. `views/settings.py` — UI
기존 `🔄 데이터 수집` / `🗃 데이터 관리` 탭 내부를 각각 서브탭으로 분리:
`st.tabs(["📰 신규 게시물", "🏛️ 정부 정책"])`.

**데이터 수집 탭 → 정부 정책 서브탭:**
- 캡션: 7개 소스 안내 (국토교통부/한국부동산원/LH/서울시/HF/HUG/SH).
- 정책 전용 수집 시각 설정 UI (브랜드용 스케줄 UI와 동일한 위젯 패턴, key 접두어만
  `policy_sched_`로 구분).
- 소스별 개별 "지금 수집" 버튼 7개 + "🔄 7곳 전체 지금 수집" 버튼(`type="primary"`).
- 진행 상황 표시: `@st.fragment(run_every=2)`로 `collector.get_policy_progress(run_id)`
  폴링, 브랜드 수집의 `_show_collection_progress`와 동일한 패턴.
- 수집 이력: `db.get_policy_run_batches(limit=50)` 표로 표시.

**데이터 관리 탭 → 정부 정책 서브탭:**
- 필터: 분류(department) 선택박스, 제목 검색, 등록일 기간 필터(체크박스+시작/종료 날짜) —
  브랜드/채널/게시일 필터는 없음(정책 데이터에 해당 개념 없음).
- 표 컬럼: 등록일 / 분류 / 제목(한 줄 말줄임) / 조회수 / 보기.
- 상세보기 팝업(`@st.dialog`): 제목/분류/등록일/조회수/원문 링크(스니펫·본문 없음, 목록
  필드만 수집하므로).
- 페이지네이션: 기존 `_render_data_management`와 동일한 처리(page_size/이전/다음/처음/끝).
- 선택 삭제 / 전체 삭제: `db.delete_policy_events` / `db.delete_all_policy_events` 사용
  (위젯 키 접두어 `policy_lookup_`).

모든 위젯 key는 브랜드용과 겹치지 않도록 `policy_` 접두어를 사용한다.

## 범위 밖
- 보도자료 상세 본문 수집(각 소스 상세 페이지) — 목록 필드로 충분한지 검증 후 별도 라운드.
- 정책 발표 ↔ 브랜드 버즈 스파이크 매핑 등 분석 기능 — 데이터가 쌓인 뒤 별도 라운드.
- 정책 소스 추가(7곳 외) — 필요 시 별도 라운드.

## 테스트 계획
- `db.py`: `insert_policy_event`(신규/중복), `get_policy_events`(department 필터/정렬),
  `delete_policy_events`, `delete_all_policy_events`, `get_policy_run_batches`(run_id 묶음).
- 크롤러 7종: 고정 HTML fixture로 `fetch_press_releases`가 필드를 정확히 추출하는지,
  네트워크 오류 시 빈 리스트를 반환하는지.
- `collector.py`: `collect_*_press_releases`가 fetch 결과를 저장하고 올바른
  fetched/inserted/skipped 요약을 반환하는지, 중복 URL을 건너뛰는지,
  `collect_all_policy_events`가 한 소스 실패 시에도 나머지를 계속 수집하는지.
- `scheduler.py`: `_tick_policy()`가 등록된 시각에만 1회 발화하는지(브랜드용 `_tick()`
  테스트와 동일 패턴).
- `views/settings.py`: 정부 정책 서브탭에 수집 버튼이 있고 클릭 시 요약이 표시되는지,
  선택 삭제/전체 삭제가 `policy_events`만 지우고 `mentions`은 그대로 두는지.
