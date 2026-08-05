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
| ⚙️ 설정 (관리자 전용) | 접근 제어(IP 화이트리스트) · 데이터 수집 · 데이터 관리 · 서버 배포 |

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

## 접근 제어

`data/access_config.json`에 등록된 IP만 접속을 허용한다(목록이 비어 있으면 부트스트랩 모드로 전체 허용).
관리자로 등록된 IP만 "설정" 메뉴를 볼 수 있다.

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

## 기술 스택

- Streamlit (`st.navigation(position="top")` 기반 멀티페이지, 오렌지 테마 커스텀 CSS)
- SQLite (수집 데이터) / JSON (키워드·스케줄·접근 제어 설정)
- requests + BeautifulSoup / stdlib `xml.etree` (RSS) — 크롤링
- Playwright(Chromium) — PDF 보고서 생성
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
access_control.py    IP 화이트리스트 · 관리자 판별
db.py               수집 데이터 SQLite 저장소
report_pdf.py        PDF 보고서 카드덱 HTML 템플릿 + Playwright PDF 생성 (미리보기와 공유)
collector.py         키워드×채널 수집 조율, 노이즈 필터링, 일회성 백필(run_backfill)
scheduler.py         자동 수집 스케줄러(백그라운드 스레드, 3개 독립 파이프라인)
utils.py             키워드/스케줄/채널 표시 설정 로드·저장, 상대 날짜 변환
crawlers/            네이버·구글·다음·디시인사이드 스크래퍼 + 네이버뉴스API(공식 API) + 정책 7개 기관
views/               페이지별 렌더 함수 (news_today, firms, briefings, search, report, settings)
data/                런타임 설정·DB (access_config.json, keywords.json, news.db 등 — git 미포함)
scripts/start_server.sh  원격 서버 기동 스크립트
```
