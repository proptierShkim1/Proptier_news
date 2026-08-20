# 프롭티어 부동산 AI 뉴스봇 (hana_p)

프롭티어(Proptier)를 위한 부동산·프롭테크 AI 뉴스 인텔리전스 대시보드. Streamlit 멀티페이지 앱으로,
매일의 주요 뉴스 브리핑부터 실제 뉴스 수집·조회·관리까지 한 곳에서 처리한다.

## 화면 구성

| 메뉴 | 설명 |
|---|---|
| 📰 오늘의 뉴스 | hero 배너, 지표 카드, 경영진 브리핑, 시간대별 분포 차트, 카테고리 탭별 랭킹 뉴스 |
| 🏢 부동산사 동향 | 기간(누적전체/1년/1개월/1주)·부동산사별 이슈 타임라인 및 이력 |
| 📝 브리핑 | 날짜별 아침 브리핑 아카이브 — 확정된 과거 날짜는 채널 표시 설정이 나중에 바뀌어도 내용이 변하지 않는다 |
| 🔍 뉴스 검색 | 키워드·기간·부동산사 필터링 검색 |
| 📄 PDF 보고서 | 표지 + 랭킹 1~5위 카드뉴스 형태(1080×1080, 6페이지) — 실제 다운로드 가능한 PDF 생성 |
| 🏛️ 정책 뉴스 | 정부 정책 보도자료 전용 화면 — hero/지표, 경영진 브리핑, 발표 추이 차트, 카테고리 탭별 점수 랭킹 |
| 🤖 AI AGENT | Gemini 기반 자유 대화형 챗봇(`st.chat_input`) — 수집 데이터(뉴스·정책)를 벡터 검색으로 찾아 답변에 근거로 사용, 지표 성격 질문(건수·비용·순위 등)은 16개 함수 호출 도구로 직접 집계해 답변, 근거가 부족하면 opt-in Hybrid Search(웹 검색) 버튼 제공 |
| ⚙️ 설정 (관리자 전용) | 접근 제어(IP 화이트리스트) · 데이터 수집 · 데이터 관리 · 벡터 데이터(백업/복구 포함) · API 사용량 · 로그 · 서버 배포 |

메뉴 순서: 오늘의 뉴스 → 부동산사 동향 → 브리핑 → 정책 뉴스 → 뉴스 검색 → PDF 보고서 → AI AGENT
→ (관리자만) 설정.

오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서 5개 화면 모두 `data/news.db`(SQLite)의
실제 수집 데이터(`mentions`)를 조회해서 렌더링한다. 카테고리 분류·점수·메달처럼 원본 데이터에
없는 표시용 필드는 `news_feed.py`가 제목/스니펫 키워드 기반 휴리스틱으로 계산한다(하드코딩된
`data.py` 샘플은 더 이상 어디서도 사용하지 않음).

부동산사 동향의 `build_issues()`는 이슈를 클러스터 생성(최초 기사) 오름차순으로 반환하므로,
`views/firms.py`가 각 이슈의 마지막 기사 시각(`articles[0][0]`) 기준 내림차순으로 다시 정렬해
최신 이슈부터 보여준다 — 정렬하지 않으면 새로 수집된 이슈가 `DISPLAY_LIMIT` 밖으로 밀려 화면에
안 보인다.

## 데이터 수집

키워드(브랜드/경쟁사/시장 키워드) × 채널 조합으로 수집한다.

- **채널**: 네이버(블로그·카페, 스크래핑), 구글 뉴스(RSS), 다음 뉴스(스크래핑), 디시인사이드(커뮤니티,
  스크래핑) — 4개는 API 키 불필요 / 네이버뉴스API(네이버 공식 뉴스 검색 API, Client ID·Secret 필요,
  `.env`의 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`) / 매경API(매일경제 뉴스 검색 API, IP
  화이트리스트 인증이라 별도 키 불필요) — 네이버뉴스API·매경API 모두 신규 게시물과 완전히
  독립된 탭·스케줄·실행 상태로 운영. 매경API는 벡터(시맨틱) 검색 방식이라 offset 파라미터가
  없어 정기 수집은 기간 제한 없이 최근 것만, 백필은 기간을 구간별로 나눠 반복 호출한다. 또한
  원문 URL 패턴이 스펙에 없어 링크를 만들지 않고, `mentions.url`(UNIQUE 제약)은 art_id 기반
  내부 식별자(`mk-api:{art_id}`)로만 채운다 — 다른 채널처럼 기사 링크로 클릭해 들어갈 수는 없다
- **노이즈 필터링**: 검색어 완전 부재 필터 → 합성어 경계 필터(예: "직방" 검색 시 파생어 제외) →
  필수 포함 키워드(부동산 문맥 단어) → 수동 제외 키워드, 4단계
- **저장**: `data/news.db`의 `mentions`(수집 기사) / `run_logs`(실행 이력) 테이블 — 채널값으로만
  구분되며 스키마는 공유
- **자동 수집**: 설정 페이지에서 채널군별로 등록한 시각(HH:MM, `/`로 구분)마다 백그라운드 스케줄러가
  자동 실행. 신규 게시물(4채널)/네이버뉴스API/매경API/정부 정책 4개가 서로 완전히 독립된 스케줄.
  네 수집 모두 `scheduler.py`의 `_tick()`이 아니라 `collector.start_background_*()`가 띄우는 별도
  데몬 스레드에서 돈다 — 예전엔 신규 게시물/정부 정책이 `_tick()` 스레드에서 동기로 실행돼, 브랜드
  수집이 오래 걸리면 그동안 정확히 `HH:MM` 일치를 요구하는 다른 스케줄(정책/네이버뉴스/벡터화)이
  그날 아예 스킵될 수 있었다.
- **일회성 백필**: `collector.run_backfill(days=30, max_pages=10)` — 구글/다음/네이버뉴스API/매경API
  4채널 한정으로 과거 최대 30일치를 소급 수집하는 운영용 함수 (UI/스케줄에는 연결하지 않음, 필요할 때
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

## 브리핑 아카이빙

설정 → 데이터 관리의 "🔎 화면 표시 채널" 토글은 다른 5개 화면(오늘의 뉴스 등)에는 실시간으로
적용되지만, **한 번 확정된 과거 브리핑에는 소급 적용되지 않는다** — 예전엔 토글을 바꾸면
이미 봤던 지난 브리핑의 채널별 수집 현황·주요 뉴스까지 그때그때 다시 계산돼 바뀌었는데, "그날
실제로 무슨 일이 있었는지"를 나중에 되짚어보는 아카이브 용도로는 부적절한 동작이었다.

- `news_feed.archive_pending_briefings()`가 스케줄러 tick마다 "데이터는 있지만 아직 확정 안
  된" 과거 날짜(오늘 제외)를 찾아 `db.briefing_archives` 테이블에 그날의 채널별 수집
  현황·채널별 주요 뉴스·자사/경쟁사/시장 동향을 표시용 필드 그대로 복사해 저장한다. 확정된
  이후로는 원본 `mentions`가 삭제되거나 채널 표시 설정이 바뀌어도 그 내용이 변하지 않는다.
  대상 날짜는 `db.get_distinct_mention_dates()`(실제 데이터가 있는 날짜만, gap-date는
  걸러냄)로 좁혀서 매 tick마다 전체 `mentions`를 훑지 않는다.
  오늘 날짜는 아직 확정 전이라 `views/briefings.py`가 `get_mentions_by_collected_date`로
  그 시점까지의 데이터를 즉석에서 계산해 미리보기로 보여준다(채널 표시 필터와 무관하게
  전체 채널·건수 제한 없이, 다음날 확정될 내용과 정확히 같은 기준).

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
  `page.pdf()`로 바이트를 만들고, `st.download_button`으로 내려준다. `views/report.py`는 이
  함수를 직접 호출하지 않고 캐시를 앞에 둔 `get_or_generate_pdf_bytes()`를 호출한다 — 자세한
  내용은 "성능 · 동시 접속" 섹션 참고
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
  키 목록, 매 호출마다 순서를 랜덤으로 섞은 뒤 앞에서부터 시도하다 실패하면 다음 키로
  failover — 이유는 "성능 · 동시 접속" 참고)와 `GEMINI_MODEL`(기본 `gemini-2.5-flash`)을
  사용하며, 원문(`content`)이 실제로 수집된 기사만 대상으로 한다(제목·짧은 스니펫만 있는 기사는
  근거 부족으로 요약하지 않고 기존 발췌 방식을 그대로 씀). 생성된 요약은 `mentions.summary`
  컬럼에 저장되어 같은 기사를 다시 요약하지 않는다 — `views/report.py`의 `_ensure_pdf_summaries()`가
  top5 중 `summary`가 비어있는 항목만 호출한다. 렌더링 시점에 처음 요약하면 Gemini 호출을
  기다려야 해서 첫 로딩이 느려지므로, `scheduler.py`가 5분 주기(+앱 시작 시 즉시)로 백그라운드에서
  미리 요약해 둔다(`summarizer.presummarize_top_pdf_items`) — 렌더링 경로는 대부분 이미 채워진
  요약을 그대로 쓰고 실제 호출 없이 넘어간다
- **원문 없는 기사 제외**: `news_feed.build_news_items()`는 항목마다 `has_real_content`
  플래그를 매긴다(본문 또는 제목과 다른 스니펫이 있으면 True). 구글 채널은 검색 결과
  스니펫을 항상 제목과 동일하게 주고, 뉴스 링크(`news.google.com/rss/articles/...`)도
  구글 자체 JS 페이지라 원문 URL을 서버 사이드로 못 따라가 본문 수집기가 없다 — 즉 구글
  채널 기사는 항상 `has_real_content=False`. `views/report.py`의 `_select_pdf_items()`가
  top5를 고를 때 이 플래그가 False인 항목을 미리 제외해서, "OO 채널에서 수집된 기사입니다"
  같은 안내 문구만 있는 카드가 PDF에 나가지 않게 한다(오늘의 뉴스/뉴스 검색 화면은 안내
  문구 + 원문 링크 형태로도 유용해서 그대로 둔다)

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
- **대화 이력은 `st.session_state`가 아니라 브라우저별 영구 식별자(`_client_uid`) 기준으로
  DB(`db.agent_chat_messages` 테이블, 메시지 1건 = 1행)에 저장한다.** F5 새로고침이나 다른 탭
  이동으로 브라우저 세션이 끊겨도(Streamlit의 session_state는 이때 초기화됨) "대화 초기화" 버튼을
  누르기 전까지 대화가 이어진다.
- **대화는 브라우저별 세션 목록으로 저장되어 지난 대화를 나중에 다시 볼 수 있다.** "새 대화 시작"을
  누르면 진행 중이던 대화를 지우지 않고 목록에 보존한 뒤 새 세션을 시작한다. 화면 상단의
  "🗂️ 지난 대화" 셀렉트박스로 과거 세션을 골라 읽기 전용으로 다시 볼 수 있고(입력창은 숨김),
  "🟢 현재 대화"를 고르면 이어서 채팅할 수 있다.
- **원래는 접속 IP를 사용자 식별 키로 쓰고, IP별 전체 대화를 JSON 파일 하나에 통째로 읽고 다시
  쓰는 방식이었다(`data/agent_chat_history.json`).** 100명 이상 동시 사용을 준비하며 2026-08-20에
  두 가지를 함께 바꿨다:
  1) **저장 방식** — 서로 다른 사용자가 거의 동시에 채팅할 때마다 파일 전체를 다시 쓰는 전역 락
     뒤에서 저장이 줄을 서는 게 병목이었다. 메시지 1건 = 1행짜리 DB 테이블
     (`db.append_agent_chat_message` / `db.get_agent_chat_sessions`)로 옮겨 각 저장이 독립된
     INSERT가 되도록 바꿨다. 기존 JSON 파일은 `db.migrate_agent_chat_history_json()`이
     `init_db()` 안에서 최초 1회 자동으로 읽어들여 이전하고, 원본은 `.json.migrated`로 이름만
     바꿔 보존한다.
  2) **사용자 식별 키** — 로그인이 없는 내부망 도구라 접속 IP를 식별자로 재사용했는데, 사내망
     특성상 여러 사람이 같은 IP를 공유하거나(공유기/게이트웨이) DHCP로 한 사람의 IP가 바뀔 수
     있어 대화가 섞이거나 끊길 위험이 있었다. `app.py`의 `_get_or_create_client_uid()`가
     브라우저별 영구 쿠키(`hana_p_uid`)를 발급해 그 값을 식별 키로 쓴다 — `st.context.cookies`
     (읽기 전용)로 기존 쿠키를 확인하고, 없으면 서버에서 `uuid.uuid4()`로 새로 만들어 이번
     요청에 즉시 쓰면서 `st.components.v1.html`에 심은 JS로 브라우저에 쿠키를 저장한다. 처음엔
     URL 쿼리파라미터 + 페이지 리다이렉트 방식(JS로 쿠키를 만들고 `window.parent.location`을
     바꿔 같은 URL에 `?uid=...`를 붙이는 방식)을 시도했는데, Streamlit이 컴포넌트 iframe에 심는
     `sandbox` 속성에 `allow-top-navigation`이 없어 최상위 프레임 이동이 브라우저에서 조용히
     막히는 걸 Playwright로 콘솔 에러까지 직접 확인하고 폐기했다 — `document.cookie` 쓰기는
     `allow-same-origin`만으로 막히지 않아 지금 방식으로 바꿨다. 활동 로그(`db.log_activity`)는
     여전히 접속 IP 기준이다 — "누가/언제 접속했는지"라는 감사 목적에는 IP가 더 자연스럽다.
- **사내 데이터로 답하기 어려운 질문은 opt-in Hybrid Search(웹 검색) 답변을 추가로 제공한다.**
  벡터 검색 결과 중 가장 가까운(distance가 가장 작은) 항목이 임계값(`agent_chat._INSUFFICIENT_DISTANCE_THRESHOLD=0.83`,
  실제 관련/무관 질문 여러 개로 실측해 정함 — 관련 질문은 0.69~0.80대, 무관한 질문은 0.85~0.91대에
  몰려 있었다)보다 크면 `agent_chat.is_grounding_sufficient()`가 False를 반환한다. 이때도 기존처럼
  즉시 일반 지식으로 답하되(대화가 끊기지 않음), 그 답변 아래에 "🌐 Hybrid Search 실행" 버튼을
  추가로 보여준다. 사용자가 누르면 `agent_chat.ask_with_web_search()`가 Gemini의 구글 검색 그라운딩
  도구(`types.Tool(google_search=types.GoogleSearch())`)로 같은 질문을 다시 물어 새 답변을 대화에
  이어붙인다 — 사내 데이터가 없어 애매한 답만 받고 이탈하는 걸 막기 위한 opt-in 기능.
- **지표 성격 질문은 함수 호출(automatic function calling)로 직접 집계해 답한다.**
  `agent_chat._STATS_TOOLS`에 16개 순수 함수(채널별 건수, 브랜드 언급 비교, API 비용, 벡터화
  진행률, 수집 상태, 정책 카테고리/순위 등)를 그대로 등록해두면 google-genai SDK가 시그니처와
  독스트링만으로 스키마를 만들고, 모델이 필요하다고 판단할 때 알아서 호출·재질의한다 — 별도 라우팅
  코드 없이 벡터 검색(문서 그라운딩)과 지표 조회(정확한 집계)를 한 대화 안에서 함께 쓸 수 있다.
  이 16개 도구가 부르는 `db.py` 조회는 `cached_db.py`에 60초 TTL로 캐싱해 여러 사용자가 비슷한
  질문을 해도 DB 재조회를 줄인다. 또한 "몇 건", "API 비용", "벡터화 현황" 같은 키워드로 명백한
  지표 질문임을 판별하면(`agent_chat.looks_like_stats_only_question`) 벡터 검색(임베딩 API 호출
  2회)을 아예 건너뛴다 — 동시 사용자가 늘어날수록 Gemini API 키 풀에 걸리는 부담을 줄이기 위함
  (애매하면 항상 그라운딩을 시도해 근거 누락을 우선 방지).

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
- **PDF 생성 콘텐츠 캐시 + single-flight 락** (`report_pdf.py`의 `get_or_generate_pdf_bytes()`) —
  "PDF 생성"을 누르면 매번 Playwright로 Chromium을 새로 띄웠다. 이 페이지엔 날짜·채널 필터가
  없어 같은 시점엔 모든 사용자가 동일한 top5를 보므로, 동시에 여러 명이 누르면 똑같은 내용을
  위해 크로미움을 중복으로 띄우는 낭비가 생긴다. 캐시 키는 손으로 고른 필드가 아니라 실제로
  렌더링되는 `build_deck_html()` 결과의 SHA-256 해시다 — 표지의 날짜(`datetime.now()`)나
  카드별 최신성 문구(12시간 컷오프로 바뀌는 문구)처럼 렌더러가 읽는 모든 필드가 구조적으로
  키에 반영되어, top5/집계가 같아도 날짜가 바뀌면 자동으로 재생성된다. 모듈 전역 캐시 슬롯
  하나(`_cache: tuple[str, bytes] | None`)를 서버 프로세스 전체가 공유하며, `threading.Lock()`
  기반 double-checked locking으로 콜드 캐시에 동시에 들어온 요청들이 Chromium을 한 번만
  띄우고 결과를 나눠 받는다. `collector.py`/`scheduler.py`에는 캐시 무효화 호출을 추가하지
  않았다 — `cached_db`가 60초 TTL로 이미 새 데이터를 반영하므로, 새 데이터가 렌더링 결과를
  바꾸면 해시 키가 자연히 달라져 재생성된다(아래 캐시 무효화 원칙과 동일).
- **Gemini API 키 시도 순서 랜덤화** (`summarizer.py`/`vectorizer.py`의 `_load_api_keys()`) —
  기존엔 `GEMINI_API_KEYS`를 항상 같은 순서로 반환해서, 동시 요청이 몰리면 다들 1번 키부터
  두드려 그 키의 분당 한도에 먼저 걸리고 나서야 순차로 다음 키로 넘어가는 지연이 쌓였다.
  `_load_api_keys()`가 반환 직전에 `random.shuffle()`로 순서를 섞어, 매 호출마다 시도 순서가
  달라진다(호출부의 `for key in keys` failover 로직은 그대로). AI AGENT 채팅(`agent_chat.py`)도
  `summarizer._load_api_keys()`를 그대로 재사용하므로 코드 변경 없이 같은 효과를 받는다.
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

## DB 안정성 · 자동 백업/복구

2026-08-14~19에 원인이 제각각인(pandas/pyarrow 버전 조합의 세그폴트, 다른 프로세스의
OOM-kill, 배포 스크립트가 자기 자신의 서버 프로세스를 죽인 회귀, WAL 재생 타이밍 등)
`news.db` 손상이 반복됐다. 원인 하나하나를 찾아 막는 접근은 이 서버(가상화 환경, 다른
앱들과 리소스를 공유) 조건에서 한계가 있어서, **손상 자체를 막는 대신 손상돼도 사람
개입 없이 몇 분 안에 스스로 복구되는 안전망**으로 방향을 바꿨다.

- **크래시 내구성**: `db._connect()`가 매 연결마다 `PRAGMA synchronous=FULL`을 설정한다
  (journal_mode와 달리 synchronous는 DB 파일에 영구 저장되지 않아 매번 다시 설정해야
  함). 매 커밋을 확실히 디스크에 fsync해 프로세스가 쓰기 도중 죽어도 손상 가능성을
  줄인다.
- **자동 백업**: `scheduler.py`의 `_tick_db_backup`이 20분마다 `db.backup_database()`
  (SQLite 온라인 백업 API — 다른 커넥션이 쓰기 중이어도 안전하게 스냅샷을 뜬다)를
  호출해 `data/db_backups/`에 저장하고, 최근 12개만 남기고 정리한다.
- **자동 무결성 검사 + 복구**: `_tick_db_health_check`가 10분마다 `db.is_healthy()`
  (`init_db()`를 거치지 않는 순수 읽기 전용 `PRAGMA integrity_check` — 손상된 파일에
  마이그레이션을 시도하다 추가 문제를 일으키지 않기 위함)로 확인하고, 실패하면
  `db.restore_latest_backup()`이 가장 최근 백업으로 즉시 교체한다(손상 파일은
  `news.db.autofailed-*`로 타임스탬프를 붙여 보존, 사후 분석 가능). 이 앱은 매 요청마다
  `db._connect()`로 새 커넥션을 열기 때문에 파일만 원상복구하면 프로세스 재시작 없이
  바로 다음 요청부터 정상 파일을 쓴다.
- **배포 시 로컬 파일이 서버 걸 덮어쓰지 않도록**: `views/settings.py`의
  `_DATA_UPLOAD_SKIP`이 `.gitignore`의 `data/` 항목과 동일한 목록(설정 파일들,
  `vector_backups/`, `db_backups/` 등)을 배포 업로드에서 제외한다 — 예전엔 `news.db`만
  제외해서, 로컬에서 테스트하며 쌓인 `scheduler.log`/백업 파일이 배포 때마다 서버 것을
  덮어쓰고 있었다.
- **측정된 비용**: 무결성 검사 0.14초, 백업 0.66초(DB 283MB 기준) — 사용자 수와 무관하게
  파일 크기에만 비례하는 작업이라 동시 접속이 늘어도 부담이 커지지 않는다. 디스크는
  백업 12개 × DB 크기만큼 쓴다(현재 기준 약 3.4GB).
- **정직한 한계**: 이건 손상 "원인"을 없애는 게 아니라 "피해"를 최소화하는 것이다 —
  가장 최근 백업 시점 이후의 데이터(최대 20분치)는 사고마다 유실될 수 있다. 근본
  원인이 인프라(가상화 디스크의 fsync 신뢰성) 레벨일 가능성이 있어 애플리케이션
  코드만으로는 완전히 해결하지 못한다.

## 벡터 데이터 · 접속 로그 (설정 → 벡터 데이터 / 로그)

- **벡터 데이터**: `vectorizer.py`가 Gemini 임베딩 모델(`gemini-embedding-001`, 3072차원)로
  `mentions`/`policy_events`의 아직 벡터화되지 않은 항목을 임베딩해 각 테이블의 `embedding`
  컬럼(JSON 배열, 원본 보관용)과 `sqlite-vec` 색인(`mention_vectors`/`policy_vectors`, vec0
  가상 테이블, 실제 유사도 검색용)에 함께 저장한다. summarizer.py와 같은 `.env`의
  `GEMINI_API_KEYS`를 재사용하고, 매 호출마다 순서를 랜덤으로 섞은 뒤 시도하는 failover도
  동일하게 지원한다("성능 · 동시 접속" 참고). "🧬 벡터화 진행"
  버튼은 신규 게시물/네이버뉴스 수집과 같은 백그라운드 스레드 패턴(`start_background_vectorize`)
  으로 동작해 페이지를 벗어나거나 새로고침해도 계속 진행되고, 실행 이력은 `vector_run_logs`
  테이블에 남는다. 색인 테이블이 나중에 추가되었거나 유실된 경우를 위해 매 벡터화 실행마다
  `embedding` 컬럼엔 있지만 색인엔 없는 행을 자동 백필한다(`vectorizer.sync_vector_index`).
- **자동 벡터화**: 관리자가 "벡터화 진행" 버튼을 매번 누르지 않아도 되도록, 설정 → 벡터
  데이터 탭의 "⏰ 벡터화 스케줄"에서 신규 게시물/정책/네이버뉴스 API와 같은 방식(HH:MM
  시각을 `/`로 구분해 등록, 미등록 시 자동 실행 없음)으로 직접 관리한다.
  `scheduler.py`의 `_tick_auto_vectorize`가 등록된 시각에 `start_background_vectorize()`를
  호출하며, 이미 진행 중인 벡터화는 알아서 건너뛰므로 배치 하나가 오래 걸려도 겹쳐 실행되지
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
- **벡터 임베딩 백업/복구** (설정 → 벡터 데이터 탭 하단): `mention_vectors`/`policy_vectors`(vec0
  색인)는 `mentions.embedding`/`policy_events.embedding`(JSON 원본)으로부터 언제든 재생성
  가능한 파생 데이터라 백업 대상에서 빼고, url을 키로 삼은 embedding 값만 JSON 파일로
  내보낸다(`vectorizer.export_vector_backup`) — id가 아니라 url을 키로 쓰는 이유는 DB 복구
  후 id가 바뀌어도 url은 유지되기 때문. 복구 시엔 url이 일치하고 아직 embedding이 비어있는
  행에만 채워 넣고(이미 값이 있으면 덮어쓰지 않음) `vectorizer.sync_vector_index()`로 색인도
  함께 채운다 — DB 손상 등으로 색인이 날아갔을 때 Gemini 임베딩 API를 다시 호출하지 않고도
  되돌릴 수 있다. 복구 버튼을 누르면 `st.status()`로 뉴스 복구 → 정책 복구 → 색인 재생성
  단계가 실시간으로 표시된다. 건마다 새 커넥션을 여는 대신 커넥션 하나로 전체를 처리해
  수천 건 규모도 몇 초 안에 끝난다.
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
db.py               수집 데이터 SQLite 저장소 (WAL 모드 + synchronous=FULL + sqlite-vec 확장) + 벡터 색인/접속 로그 테이블 + 자동 백업·무결성검사·복구
cached_db.py        db.py 조회를 60초 TTL로 캐싱 (동시 접속·반복 상호작용 시 중복 조회 방지)
report_pdf.py        PDF 보고서 카드덱 HTML 템플릿 + Playwright PDF 생성 (미리보기와 공유)
collector.py         키워드×채널 수집 조율, 노이즈 필터링, 일회성 백필(run_backfill)
scheduler.py         자동 수집 스케줄러(백그라운드 스레드, 신규/정책/네이버뉴스/매경 + PDF 요약 미리 생성 + 벡터화 + DB 자동 백업/무결성검사)
utils.py             키워드/스케줄/채널 표시 설정 로드·저장, 상대 날짜 변환
crawlers/            네이버·구글·다음·디시인사이드 스크래퍼 + 네이버뉴스API·매경API(공식 API) + 정책 7개 기관
views/               페이지별 렌더 함수 (news_today, firms, briefings, search, report, policy_news, agent, settings)
data/                런타임 설정·DB (access_config.json, keywords.json, news.db, db_backups/, vector_backups/ 등 — git 미포함)
scripts/start_server.sh  원격 서버 기동 스크립트
```

## 프로젝트 상세 보고서 (PPT)

`hana_p_프로젝트_상세보고서.pptx` — 보고용으로 쓰는 31슬라이드 상세 보고서(2026-08-07 최신 현황
기준, 최초 작성 2026-08-05). 회사 공식 PPT 디자인 양식(주황 탭바, 로고 로크업, 표 스타일)을
그대로 따른다.

- **구성**: 1) 프로젝트 개요 2) 전체 아키텍처·코드 구조 3) 페이지 구성 및 상세 기능(7개 화면 +
  AI AGENT) 4) 관리자(설정) 페이지 상세(6개 섹션: 접근제어/데이터수집/데이터관리/벡터데이터/
  로그/배포) 5) 데이터 수집 채널(일반 5종·정책 7종) 6) 데이터 정제(필터링) 로직 및 예시
  7) DB 스키마(+ 벡터 색인·접속 로그) 8) 현재 상태·업데이트 이력·다음 단계
- **git 미포함**: 다른 로컬 산출물처럼 저장소에는 커밋하지 않고 프로젝트 루트에 파일로만
  둔다(사용자가 필요할 때 직접 열어서 확인·배포).
- **갱신 방법**: python-pptx 스크립트로 생성한다 — 표지/목차/섹션 헤더/불릿(`■`/`-`, `**강조**`
  빨간 굵게, `` `code` `` 고정폭)·표(헤더 회색, 짝수행 음영)를 만드는 헬퍼 함수들을 재사용해
  슬라이드별 텍스트만 바꿔서 재생성하는 방식. 로고는 기존 pptx에서 추출한 이미지를 그대로
  삽입한다. 코드 변경사항이 누적되면 이 보고서도 같은 방식으로 다시 갱신이 필요할 수 있다.
- **시각 검증**: PowerPoint COM 자동화(`PowerPoint.Application` + `Presentation.SaveAs(..., 18)`
  = PNG)로 슬라이드 전체를 이미지로 내보내 실제 렌더링을 눈으로 확인한 뒤 완료 처리한다.
