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
| 📄 PDF 보고서 | 상위 랭킹 뉴스 인쇄용 미리보기 |
| ⚙️ 설정 (관리자 전용) | 접근 제어(IP 화이트리스트) · 데이터 수집 · 데이터 관리 · 서버 배포 |

오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서는 `data.py`의 샘플 데이터를 사용한다.
설정 > 데이터 수집에서 실행하는 실제 뉴스 수집은 별도의 `data/news.db`(SQLite)에 저장되며,
아직 화면 표시 데이터와 연결되어 있지 않다.

## 데이터 수집

키워드(브랜드/경쟁사/시장 키워드) × 채널 조합으로 API 키 없이 스크래핑한다.

- **채널**: 네이버(블로그·카페), 구글 뉴스(RSS), 다음 뉴스, 디시인사이드(커뮤니티)
- **노이즈 필터링**: 검색어 완전 부재 필터 → 합성어 경계 필터(예: "직방" 검색 시 파생어 제외) →
  필수 포함 키워드(부동산 문맥 단어) → 수동 제외 키워드, 4단계
- **저장**: `data/news.db`의 `mentions`(수집 기사) / `run_logs`(실행 이력) 테이블
- **자동 수집**: 설정 페이지에서 등록한 시각(HH:MM, `/`로 구분)마다 백그라운드 스케줄러가 자동 실행

설정 페이지의 "데이터 관리" 탭에서 브랜드/채널/제목/수집일로 필터링해 조회하고,
개별 또는 전체 삭제할 수 있다.

## 접근 제어

`data/access_config.json`에 등록된 IP만 접속을 허용한다(목록이 비어 있으면 부트스트랩 모드로 전체 허용).
관리자로 등록된 IP만 "설정" 메뉴를 볼 수 있다.

## 기술 스택

- Streamlit (`st.navigation(position="top")` 기반 멀티페이지, 오렌지 테마 커스텀 CSS)
- SQLite (수집 데이터) / JSON (키워드·스케줄·접근 제어 설정)
- requests + BeautifulSoup / stdlib `xml.etree` (RSS) — 크롤링
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

## 디렉터리 구조

```
app.py              진입점 — 접근 제어, DB 초기화, 스케줄러 기동, 페이지 라우팅
theme.py            공통 CSS(오렌지 테마) 및 재사용 컴포넌트
data.py             오늘의 뉴스/부동산사 동향/브리핑 등 샘플 데이터
access_control.py    IP 화이트리스트 · 관리자 판별
db.py               수집 데이터 SQLite 저장소
collector.py         키워드×채널 수집 조율, 노이즈 필터링
scheduler.py         자동 수집 스케줄러(백그라운드 스레드)
utils.py             키워드/스케줄 설정 로드·저장, 상대 날짜 변환
crawlers/            네이버·구글·다음·디시인사이드 스크래퍼
views/               페이지별 렌더 함수 (news_today, firms, briefings, search, report, settings)
data/                런타임 설정·DB (access_config.json, keywords.json, news.db 등 — git 미포함)
scripts/start_server.sh  원격 서버 기동 스크립트
```
