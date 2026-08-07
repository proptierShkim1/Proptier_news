# 프롭티어 부동산 AI 뉴스봇 (hana_p)

프롭티어(Proptier)를 위한 부동산·프롭테크 AI 뉴스 인텔리전스 대시보드. Streamlit 멀티페이지 앱으로,
매일의 주요 뉴스 브리핑부터 실제 뉴스 수집·조회·관리까지 한 곳에서 처리한다.

## 화면 구성

| 메뉴 | 설명 |
|---|---|
| 📰 오늘의 뉴스 | hero 배너, 지표 카드, 경영진 브리핑, 시간대별 분포 차트, 카테고리 탭별 랭킹 뉴스 |
| 🏢 부동산사 동향 | 기간(누적전체/1년/1개월/1주)·부동산사별 이슈 타임라인 및 이력 |
| 📝 브리핑 | 날짜별 아침 브리핑 아카이브 |
| 🔍 뉴스 검색 | 키워드·기간·부동산사 필터링 검색 |
| 📄 PDF 보고서 | 표지 + 랭킹 1~5위 카드뉴스 형태(1080×1080, 6페이지) — 실제 다운로드 가능한 PDF 생성 |
| 🏛️ 정책 뉴스 | 정부 정책 보도자료 전용 화면 — hero/지표, 경영진 브리핑, 발표 추이 차트, 카테고리 탭별 점수 랭킹 |
| 🤖 AI AGENT | Gemini 기반 자유 대화형 챗봇(`st.chat_input`) — 수집 데이터(뉴스·정책)를 벡터 검색으로 찾아 답변에 근거로 사용 |
| ⚙️ 설정 (관리자 전용) | 접근 제어(IP 화이트리스트) · 데이터 수집 · 데이터 관리 · 벡터 데이터 · 로그 · 서버 배포 |

메뉴 순서: 오늘의 뉴스 → 부동산사 동향 → 브리핑 → 정책 뉴스 → 뉴스 검색 → PDF 보고서 → AI AGENT
→ (관리자만) 설정.

오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서 5개 화면 모두 `data/news.db`(SQLite)의
실제 수집 데이터(`mentions`)를 조회해서 렌더링한다. 카테고리 분류·점수·메달처럼 원본 데이터에
없는 표시용 필드는 `news_feed.py`가 제목/스니펫 키워드 기반 휴리스틱으로 계산한다(하드코딩된
`data.py` 샘플은 더 이상 어디서도 사용하지 않음).

## 데이터 수집

키워드(브랜드/경쟁사/시장 키워드) × 채널 조합으로 수집한다.

- **채널**: 네이버(블로그·카페, 스크래핑), 구글 뉴스(RSS), 다음 뉴스(스크래핑), 디시인사이드(커뮤니티,
  스크래핑) — 4개는 API 키 불필요 / 네이버뉴스API(네이버 공식 뉴스 검색 API, Client ID·Secret 필요,
  `.env`의 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`) — 신규 게시물과 완전히 독립된 탭·스케줄·실행 상태로 운영
- **노이즈 필터링**: 검색어 완전 부재 필터 → 합성어 경계 필터(예: "직방" 검색 시 파생어 제외) →
  필수 포함 키워드(부동산 문맥 단어) → 수동 제외 키워드, 4단계
- **저장**: `data/news.db`의 `mentions`(수집 기사) / `run_logs`(실행 이력) 테이블 — 채널값으로만
  구분되며 스키마는 공유
- **자동 수집**: 설정 페이지에서 채널군별로 등록한 시각(HH:MM, `/`로 구분)마다 백그라운드 스케줄러가
  자동 실행. 신규 게시물(4채널)/네이버뉴스API/정부 정책 3개가 서로 완전히 독립된 스케줄
- **일회성 백필**: `collector.run_backfill(days=30, max_pages=10)` — 구글/다음/네이버뉴스API 3채널
  한정으로 과거 최대 30일치를 소급 수집하는 운영용 함수 (UI/스케줄에는 연결하지 않음, 필요할 때
  직접 호출)

설정 페이지의 "데이터 관리" 탭에서 브랜드/채널/제목/수집일로 필터링해 조회하고,
개별 또는 전체 삭제할 수 있다. 같은 탭 상단의 "🔎 화면 표시 채널" 체크박스로 채널을 끄면
(수집·저장은 계속되지만) 오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서 5개 화면에서만
그 채널의 데이터가 즉시 제외된다.

## 정부 정책 데이터 수집

브랜드 언급 수집과는 완전히 독립된 두 번째 수집 파이프라인. 국토교통부·한국부동산원·LH·
서울시(정보소통광장)·HF(한국주택금융공사)·HUG(주택도시보증공사)·SH(서울주택도시공사) 7곳의
보도자료를 크롤링한다.

- **저장**: `data/news.db`의 `policy_events`(수집 보도자료) / `policy_run_logs`(실행 이력) 테이블 —
  브랜드 수집의 `mentions`/`run_logs`와 별도
- **자동 수집**: 설정 페이지 "데이터 수집 > 정부 정책" 탭에서 등록한 시각(브랜드 수집과 별도의
  스케줄)마다 백그라운드로 7곳을 순서대로 수집. 시각이 하나도 등록되지 않은 상태가 기본값이므로,
  등록 전까지는 자동 수집이 실행되지 않는다(화면에 경고 표시) — "지금 수집" 버튼으로 수동 실행 가능
- **조회/삭제**: 설정 페이지 "데이터 관리 > 정부 정책" 탭에서 분류/제목/등록일로 필터링해 조회하고,
  개별 또는 전체 삭제 가능 (브랜드 조회 탭과 동일한 페이지네이션 UI 공유)
- **정책 뉴스 화면**: `policy_feed.py`가 보도자료 제목 키워드로 5개 카테고리(규제·법령/지원·사업/
  통계·조사/조직·인사/행사·홍보)를 분류하고 최신성·조회수 기반 점수/메달을 매겨, `news_today.py`와
  동일한 패턴(Executive Brief·발표 추이 차트·카테고리 탭·점수 랭킹 카드)으로 `views/policy_news.py`에서
  렌더링한다

## 접근 제어

`data/access_config.json`에 등록된 IP만 접속을 허용한다(목록이 비어 있으면 부트스트랩 모드로 전체 허용).
관리자로 등록된 IP만 "설정" 메뉴를 볼 수 있다.

**알려진 한계:** 로그인 없이 접속 IP만으로 인증하므로, 같은 네트워크에서 허용된 IP를
그대로 이어받으면(예: DHCP 재할당) 별도 인증 없이 접근할 수 있다 — 사내망 자체의
안전성을 전제로 하는 구조다.

**설정 → 데이터 관리의 조회 목록 제목 이스케이프** (`views/settings.py`의
`_escape_html_attr`) — 브랜드/정책 조회 탭에서 제목을 `title="..."` 속성으로 보여줄 때
`&`/`<`/`>`/`"`를 모두 이스케이프한다(`&`를 가장 먼저 치환). 크롤링된 외부 기사 제목은
신뢰할 수 없는 텍스트라, 큰따옴표를 이스케이프하지 않으면 속성값을 이탈해 임의 HTML을
주입할 수 있었다(과거엔 `<`/`>`만 이스케이프해서 이 구멍이 남아 있었음).

## PDF 보고서

`report_pdf.py`가 화면 미리보기(`views/report.py`)와 실제 PDF 내보내기가 공유하는 HTML/CSS
카드덱 템플릿을 한 곳에 정의한다 — 레이아웃을 두 군데서 따로 관리하지 않는다.

- **구성**: 표지 1장(통계·키워드 칩) + 랭킹 1~5위 카드 5장 = 총 6페이지, 1080×1080 정사각형
  (원본 사이트가 실제로 제공하는 `report.pdf`와 동일한 카드뉴스 포맷)
- **미리보기**: `build_deck_html()`이 반환하는 콘텐츠 HTML을 `st.markdown`으로 렌더링. CSS(`DECK_CSS`)는
  `app.py`에서 `theme.inject()` 직후 전역으로 한 번만 주입한다 — `st.markdown` 안에 `<style>` 태그를
  직접 넣으면 태그 내용이 본문에 텍스트로 노출되는 Streamlit 특성이 있어 이렇게 분리했다
- **PDF 생성**: `generate_pdf_bytes()`가 Playwright(Chromium 헤드리스)로 같은 HTML을 렌더링해
  `page.pdf()`로 바이트를 만들고, `st.download_button`으로 내려준다
- **Windows 전용 이슈**: Streamlit 서버(Tornado)가 프로세스 전역 asyncio 정책을 `SelectorEventLoop`로
  강제해두는데, Playwright 동기 API는 브라우저를 서브프로세스로 띄우려면 `ProactorEventLoop`가 필요하다
  (`SelectorEventLoop`는 Windows에서 서브프로세스 생성 미지원 → `NotImplementedError`). `generate_pdf_bytes()`
  안에서 Playwright 호출 구간만 일시적으로 정책을 Proactor로 바꿨다가 끝나면 원복한다 (리눅스 배포 서버에는
  해당 없음 — `sys.platform == "win32"`로만 분기)
- **배포 시 필수**: 원격 서버에는 `pip install`만으로는 브라우저 바이너리가 안 깔린다.
  최초 1회 `{venv}/bin/playwright install chromium`을 반드시 실행해야 한다 (현재 배포된
  `192.168.10.169` 서버에는 이미 설치되어 있음)
- **AI 요약(Gemini)**: 상세 카드의 핵심 요약(`gist`)은 PDF에 실제로 나오는 상위 5건에 한해서만
  Gemini로 생성한다 — 전체 수집 기사를 대상으로 하면 대부분 PDF에 나오지도 않을 항목까지
  호출하는 낭비가 생기기 때문. `summarizer.py`가 `.env`의 `GEMINI_API_KEYS`(콤마로 구분한
  키 목록, 한 키 실패 시 다음 키로 자동 failover)와 `GEMINI_MODEL`(기본 `gemini-2.5-flash`)을
  사용하며, 원문(`content`)이 실제로 수집된 기사만 대상으로 한다(제목·짧은 스니펫만 있는 기사는
  근거 부족으로 요약하지 않고 기존 발췌 방식을 그대로 씀). 생성된 요약은 `mentions.summary`
  컬럼에 저장되어 같은 기사를 다시 요약하지 않는다 — `views/report.py`의 `_ensure_pdf_summaries()`가
  top5 중 `summary`가 비어있는 항목만 호출한다. 렌더링 시점에 처음 요약하면 Gemini 호출을
  기다려야 해서 첫 로딩이 느려지므로, `scheduler.py`가 5분 주기(+앱 시작 시 즉시)로 백그라운드에서
  미리 요약해 둔다(`summarizer.presummarize_top_pdf_items`) — 렌더링 경로는 대부분 이미 채워진
  요약을 그대로 쓰고 실제 호출 없이 넘어간다

## AI AGENT (Gemini 챗봇)

`agent_chat.py` + `views/agent.py` — `st.chat_input`/`st.chat_message` 기반 자유 대화 챗봇.
summarizer.py와 같은 `.env`의 `GEMINI_API_KEYS`/`GEMINI_MODEL`을 재사용한다. 수집 데이터
(mentions·policy_events) 벡터 검색으로 관련 문서를 찾아 답변 근거로 쓴다 — 자세한 내용은
"벡터 데이터 · 접속 로그" 섹션의 "AI AGENT 벡터 검색 연동" 참고.

- **대화 이력은 순수 텍스트로만 보관하고, 매 메시지마다 새 `genai.Client`/`chats` 세션을
  만들어 이전 대화를 주입한다.** google-genai의 `chat` 세션 객체를 `st.session_state`에 그대로
  들고 있다가 재사용하면 내부 HTTP 클라이언트가 닫힌 상태로 남아 "Cannot send a request, as the
  client has been closed" 오류가 나는 걸 실제로 확인했다 — Streamlit이 재실행마다 다른 스레드에서
  스크립트를 돌릴 수 있어서인 것으로 보임. 매번 새로 만들면 이 문제가 없고, 여러 키로
  failover하기도 더 쉽다.
- **대화 이력은 `st.session_state`가 아니라 접속 IP 기준 파일(`data/agent_chat_history.json`)에
  저장한다.** 이 앱은 로그인이 없고 IP 기반 접근 제어만 있어서, IP를 기존 `access_control.py`와
  같은 방식의 사용자 식별 키로 재사용했다. F5 새로고침이나 다른 탭 이동으로 브라우저 세션이
  끊겨도(Streamlit의 session_state는 이때 초기화됨) "대화 초기화" 버튼을 누르기 전까지 대화가
  이어진다.
- **대화는 IP당 세션 목록으로 저장되어 지난 대화를 나중에 다시 볼 수 있다.** "새 대화 시작"을
  누르면 진행 중이던 대화를 지우지 않고 목록에 보존한 뒤 새 세션을 시작한다. 화면 상단의
  "🗂️ 지난 대화" 셀렉트박스로 과거 세션을 골라 읽기 전용으로 다시 볼 수 있고(입력창은 숨김),
  "🟢 현재 대화"를 고르면 이어서 채팅할 수 있다. 세션 분리 이전(초기 버전)에 저장된 옛 형식
  파일도 진행 중인 대화 하나로 자동 마이그레이션한다(`utils.load_agent_chat_sessions`).

## 성능 · 동시 접속

여러 명이 동시에 쓸 걸 대비해 점검하고 고친 부분:

- **SQLite WAL 모드 + 연결 타임아웃 30초** (`db.py`) — 기본 롤백저널 모드는 쓰기 중에 읽기까지
  막아서 동시 접속이 늘면 "database is locked" 오류 위험이 커진다. WAL 모드는 읽기가 쓰기를
  막지 않는다(쓰기끼리는 여전히 직렬화됨).
- **DB 조회 60초 TTL 캐싱** (`cached_db.py`) — Streamlit은 위젯 값이 바뀔 때마다(검색어 입력,
  필터 변경, 브리핑 날짜 선택 등) 스크립트를 처음부터 다시 실행한다. 캐싱 전에는 그때마다 DB를
  다시 조회하고 카테고리 분류·이슈 클러스터링까지 처음부터 재계산했다 — 오늘의뉴스/부동산사동향/
  브리핑/뉴스검색/PDF보고서/정책뉴스 6개 화면 모두. 지금은 같은 조회 조건이면 여러 사용자가
  동시에 봐도, 또는 같은 사용자가 반복 상호작용해도 캐시를 공유한다. 관리자가 데이터를 삭제하면
  (`views/settings.py`) 캐시를 즉시 비워서 삭제가 최대 60초 늦게 반영되는 걸 막는다.
- **카테고리 분류 캐싱** (`news_feed.categorize()`/`policy_feed.categorize()`에 `lru_cache`) —
  지표/브리핑/이슈펄스/액션레이더 등 여러 함수가 같은 mention의 제목·스니펫을 각자 다시
  분류하던 걸 캐싱으로 줄였다(렌더링 한 번에 최대 4배 중복 계산).
- **PDF AI 요약도 같은 캐시 무효화 원칙을 따른다** (`views/report.py`) — 새로 요약을 만들면
  `cached_db`도 함께 비워, 60초 안에 다른 사용자가 같은 항목을 중복 요약 호출하는 걸 줄인다.
- **설정 화면 탭 전환 시 선택 안 된 탭은 렌더링 건너뛰기** (`views/settings.py`의
  `_render_lazy_tabs`) — `st.tabs()`는 선택 여부와 무관하게 모든 `with tab:` 블록을 매번
  실행한다. "데이터 관리"처럼 수천 건짜리 DataFrame을 조회하는 무거운 탭이 섞여 있으면
  다른 탭만 보려 해도 매번 같이 돌아가 설정 화면 전체가 10초 이상 걸렸다. 실제로 선택된
  탭의 렌더 함수만 호출하도록 바꿔 전환 시간을 1.6~2초로 줄였다(최상위 탭 + 데이터
  수집/데이터 관리의 중첩 탭 모두 적용). 선택된 탭 판단은 `st.query_params`가 아니라
  `st.tabs(key=...)`가 채우는 `st.session_state[key]`로 한다 — 쿼리 파라미터는 `on_change`
  콜백이 채우는데 클릭과 갱신 사이에 브라우저 주소창 반영 지연이 있어서, 그 사이 렌더에서는
  화면 전체가 빈 채로 나오는 버그가 있었다.

**아직 다루지 않은 부분(의도적으로 보류):** 자동/수동 수집이 백그라운드 스레드에서 끝나는
시점에 캐시를 비우는 것(감지 훅이 필요해 복잡도 대비 이득이 적다고 판단, 60초면 자연히
해소됨), 뉴스 검색/부동산사 동향 검색어 입력의 debounce.

## 벡터 데이터 · 접속 로그 (설정 → 벡터 데이터 / 로그)

- **벡터 데이터**: `vectorizer.py`가 Gemini 임베딩 모델(`gemini-embedding-001`, 3072차원)로
  `mentions`/`policy_events`의 아직 벡터화되지 않은 항목을 임베딩해 각 테이블의 `embedding`
  컬럼(JSON 배열, 원본 보관용)과 `sqlite-vec` 색인(`mention_vectors`/`policy_vectors`, vec0
  가상 테이블, 실제 유사도 검색용)에 함께 저장한다. summarizer.py와 같은 `.env`의
  `GEMINI_API_KEYS`를 재사용하고, 여러 키 순차 failover도 동일하게 지원한다. "🧬 벡터화 진행"
  버튼은 신규 게시물/네이버뉴스 수집과 같은 백그라운드 스레드 패턴(`start_background_vectorize`)
  으로 동작해 페이지를 벗어나거나 새로고침해도 계속 진행되고, 실행 이력은 `vector_run_logs`
  테이블에 남는다. 색인 테이블이 나중에 추가되었거나 유실된 경우를 위해 매 벡터화 실행마다
  `embedding` 컬럼엔 있지만 색인엔 없는 행을 자동 백필한다(`vectorizer.sync_vector_index`).
- **자동 벡터화**: 관리자가 "벡터화 진행" 버튼을 매번 누르지 않아도 되도록,
  `scheduler.py`가 10분 주기(+앱 시작 시 즉시)로 자동 벡터화를 실행한다(`_tick_auto_vectorize`,
  신규 게시물/정책/네이버뉴스 API 자동 수집과는 독립된 스케줄). `start_background_vectorize()`가
  이미 진행 중인 벡터화는 알아서 건너뛰므로, 배치 하나가 주기보다 오래 걸려도 겹쳐 실행되지
  않는다.
- **AI AGENT 벡터 검색 연동**: 질문이 들어오면 `vectorizer.search_similar_mentions`/
  `search_similar_policy_events`가 질문을 임베딩해 `mention_vectors`/`policy_vectors`에서
  코사인 거리가 가까운 문서를 상위 N개(뉴스 5·정책 3) 찾는다. 이 결과를
  `agent_chat.build_grounding_context()`로 텍스트 블록으로 만들어, 화면에 보이는 대화
  히스토리에는 섞지 않고 **그 턴의 system_instruction에만** 근거 자료로 주입한다(매 호출마다
  새 세션을 만드는 기존 구조 덕분에 턴마다 다른 검색 결과를 자연스럽게 반영). 관련 문서가
  없으면(색인이 비어있거나 유사도가 낮으면) 예전처럼 일반 지식으로 답하고 사내 데이터 기반이
  아니라는 점을 밝히도록 폴백한다.
- **sqlite-vec 확장**: `db._connect()`가 매 연결마다 확장을 로드해서(`sqlite_vec.load`)
  `mention_vectors`/`policy_vectors` 가상 테이블(`vec0`, 컬럼 차원 `db.VECTOR_DIM=3072`)을
  쓸 수 있게 한다. vec0는 rowid 충돌에 `INSERT OR REPLACE`를 지원하지 않아 upsert는
  DELETE 후 INSERT로 처리한다(`db._upsert_vector`). rowid를 `mentions.id`/`policy_events.id`와
  그대로 맞춰서 JOIN으로 원본 행을 바로 가져온다.
- **접속 로그**: `db.activity_log` 테이블에 접속 IP·화면·행위·상세내용을 남긴다. 페이지
  방문(전체 화면 공통, `app.py`), 뉴스 검색(검색어), AI 채팅 전송, PDF 생성, 관리자 작업
  (수집 실행/데이터 삭제/벡터화 실행)을 기록한다. 페이지 방문·검색은 Streamlit이 위젯
  상호작용마다 스크립트를 처음부터 다시 실행하는 특성상 매 rerun마다 기록하면 로그가
  넘치므로, `st.session_state`에 마지막으로 기록한 값을 저장해두고 값이 실제로 바뀔 때만
  남긴다. 설정 화면의 "로그" 탭에서 IP 필터·검색어·표시 개수·페이지네이션으로 조회할 수
  있다(`_render_pagination_controls` 등 기존 조회 탭과 같은 UI 패턴 재사용).

## 기술 스택

- Streamlit (`st.navigation(position="top")` 기반 멀티페이지, 오렌지 테마 커스텀 CSS)
- SQLite (수집 데이터) / JSON (키워드·스케줄·접근 제어 설정)
- sqlite-vec — SQLite 확장(vec0 가상 테이블)으로 임베딩 유사도 검색(AI AGENT 벡터 검색)
- requests + BeautifulSoup / stdlib `xml.etree` (RSS) — 크롤링
- Playwright(Chromium) — PDF 보고서 생성
- google-genai (Gemini) — PDF 상위 5건 기사 요약, AI AGENT 대화·벡터 검색, 뉴스·정책 벡터화
- paramiko (SSH/SFTP) — 원격 서버 배포

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py --server.address 192.168.14.222 --server.port 7000
```

또는 프로젝트 루트의 `hana_p.bat`을 실행하면 Windows Terminal에서 서버와 Claude Code가 각각의 탭으로 뜨고,
잠시 후 브라우저가 자동으로 열린다.

## 서버 배포

`.env`에 `DEPLOY_HOST`/`DEPLOY_SSH_PORT`/`DEPLOY_USER`/`DEPLOY_PASS`/`DEPLOY_REMOTE_PATH`/`DEPLOY_APP_PORT`를
설정한 뒤, 설정 > 배포 탭의 "서버에 배포" 버튼으로 코드 업로드 + 패키지 설치 + Streamlit 기동까지 자동 수행한다.
최초 배포 시 원격에 가상환경을 생성하고, 이후 배포마다 `requirements-server.txt` 기준으로 패키지를 갱신한다.

새 서버로 처음 배포하는 경우 PDF 보고서 기능을 쓰려면 배포 후 한 번 더 SSH로 접속해
`{DEPLOY_REMOTE_PATH}/venv/bin/playwright install chromium`을 수동 실행해야 한다 (브라우저 바이너리는
`requirements-server.txt`의 `playwright` pip 패키지만으로는 설치되지 않는다).

## 디렉터리 구조

```
app.py              진입점 — 접근 제어, DB 초기화, 스케줄러 기동, 페이지 라우팅
theme.py            공통 CSS(오렌지 테마) 및 재사용 컴포넌트
data.py             (레거시, 미사용) 과거 샘플 데이터 — 현재 어떤 화면도 참조하지 않음
news_feed.py        mentions 원본 → 화면 표시용 가공 (카테고리 분류·점수·메달·이슈·브리핑, 채널 표시 필터)
policy_feed.py      policy_events 원본 → 화면 표시용 가공 (정책 카테고리 분류·점수·메달·발표 추이)
summarizer.py       PDF 상위 5건 전용 Gemini 기사 요약 (원문 있는 기사만, 결과는 DB에 캐싱)
agent_chat.py       AI AGENT 페이지용 범용 Gemini 대화 (매 메시지마다 새 세션에 이력 주입 + 벡터 검색 근거 주입)
vectorizer.py       mentions/policy_events Gemini 임베딩 벡터화(+sqlite-vec 색인) · 백그라운드 실행/이력 · 유사도 검색
access_control.py    IP 화이트리스트 · 관리자 판별
db.py               수집 데이터 SQLite 저장소 (WAL 모드 + sqlite-vec 확장) + 벡터 색인/접속 로그 테이블
cached_db.py        db.py 조회를 60초 TTL로 캐싱 (동시 접속·반복 상호작용 시 중복 조회 방지)
report_pdf.py        PDF 보고서 카드덱 HTML 템플릿 + Playwright PDF 생성 (미리보기와 공유)
collector.py         키워드×채널 수집 조율, 노이즈 필터링, 일회성 백필(run_backfill)
scheduler.py         자동 수집 스케줄러(백그라운드 스레드, 신규/정책/네이버뉴스 + PDF 요약 미리 생성)
utils.py             키워드/스케줄/채널 표시 설정 로드·저장, 상대 날짜 변환
crawlers/            네이버·구글·다음·디시인사이드 스크래퍼 + 네이버뉴스API(공식 API) + 정책 7개 기관
views/               페이지별 렌더 함수 (news_today, firms, briefings, search, report, policy_news, agent, settings)
data/                런타임 설정·DB (access_config.json, keywords.json, news.db 등 — git 미포함)
scripts/start_server.sh  원격 서버 기동 스크립트
```
