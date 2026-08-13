# 브리핑 아카이빙 — 설계

## 배경

`views/briefings.py`의 "브리핑 아카이브"는 이름과 달리 실제로는 아카이브(고정된 과거 기록)가
아니다. `news_feed.build_briefings()`가 매 렌더링마다 **현재** 채널 표시 설정
(`news_feed.enabled_channels()`)으로 전체 `mentions`를 다시 걸러서 수집일(`collected_at`)
기준으로 묶어 만든다. 스냅샷이 없어서:

- 채널 표시(노출) 토글을 나중에 바꾸면, 이미 봤던 과거 날짜의 브리핑 내용도 그 즉시 바뀐다.
- 요약도 "제목 두 개 나열 + N건 수집" 수준의 한 줄짜리라 실질적인 브리핑이라 보기 어렵다.

사용자가 원하는 것: 하루가 끝나면 그날의 기록이 **그대로 고정**되어, 이후 채널 토글이나
데이터 변경과 무관하게 항상 같은 내용을 보여주는 진짜 아카이브. 내용은 채널별 수집 현황,
채널별 주요 뉴스, 그리고 브랜드 역할별(자사/경쟁사/시장) 동향까지 포함한다.

## 범위

이번 라운드는 "일별 브리핑 확정(freeze) 파이프라인 + 저장 + 화면 반영"만 다룬다.
브리핑 문구를 Gemini로 생성하는 것(AI 요약 문단), 브리핑 알림, 브리핑 공유/내보내기
기능은 범위 밖.

## 결정된 사항

1. **확정 시점**: 스케줄러가 도는 매 tick마다 "아직 확정 안 된, 오늘이 아닌 과거 날짜"가
   있으면 즉시 확정한다. 정확한 "23:59"/"00:00" 같은 특정 분(分)을 정확히 맞추는 방식이
   아니다 — 스케줄러 tick을 한 번이라도 놓치면 그 날짜가 영영 확정되지 않는 위험을 피하기
   위함이다. 이 방식은 최초 배포 시 이미 쌓여있던 과거 미확정 날짜를 한 번에 소급
   확정(백필)하는 효과도 자동으로 낸다. 오늘 날짜는 절대 확정하지 않는다(아직 진행 중).
2. **불변성**: 한 번 확정된 날짜는 재생성 불가. `date`를 PK로 두고 `INSERT OR IGNORE`로
   저장해, 이미 있으면 조용히 스킵한다(동시 tick 경합에도 안전).
3. **채널 노출 설정과 무관**: 확정 시점에 **전체 채널**의 데이터를 기준으로 콘텐츠를
   계산해 저장한다. 이후 채널 표시 토글을 켜고 꺼도 이미 확정된 브리핑의 내용은 전혀
   바뀌지 않는다(사용자가 지적한 핵심 문제의 해결책).
4. **원본 삭제와 무관**: 아카이브는 `mention_id`를 참조하는 게 아니라 제목/URL/브랜드/
   채널/발행일/짧은 발췌 등 표시에 필요한 내용을 그대로 복사해서 저장한다. 나중에
   "데이터 관리"에서 원본 mention을 삭제해도 이미 확정된 브리핑은 영향받지 않는다.
5. **콘텐츠 구성** (모두 기존 `news_feed._score()` 점수 로직 재사용 — 카테고리 매칭
   개수×2 + 그날 기준 최근성 +3 + 자사 브랜드 +1):
   - 채널별 수집 현황: 채널별 단순 건수
   - 채널별 주요 뉴스: 전체 mentions에 점수를 매겨 채널별로 그룹핑 후 top3
   - 프롭티어 관련 뉴스: `role: "own"` 브랜드만 top5
   - 경쟁사 동향: `role: "competitor"` 브랜드만 top5
   - 시장 동향: `role: "market"` 브랜드(AI/부동산AI/프롭테크)만 top5 — 전체 데이터를
     빠짐없이 아카이빙하기 위해 추가

## 구현 범위

### 1. `db.py` — 저장소

```sql
CREATE TABLE IF NOT EXISTS briefing_archives (
    date              TEXT PRIMARY KEY,
    channel_counts    TEXT NOT NULL,   -- JSON: {channel: count}
    channel_top_news  TEXT NOT NULL,   -- JSON: {channel: [item, ...]}
    own_brand_news    TEXT NOT NULL,   -- JSON: [item, ...]
    competitor_news   TEXT NOT NULL,   -- JSON: [item, ...]
    market_news       TEXT NOT NULL,   -- JSON: [item, ...]
    total_count       INTEGER NOT NULL,
    archived_at       TEXT NOT NULL
);
```

`item` 형태: `{title, url, brand, channel, posted_at, signal, desc}` — `desc`는
`build_news_items()`가 반환하는 `desc` 리스트의 첫 번째 문자열(짧은 발췌 하나)만 뽑아
평범한 문자열로 저장한다. 나머지 필드도 `build_news_items()` 결과에서 그대로 가져온다.

새 함수:
- `insert_briefing_archive(record: dict) -> bool` — `INSERT OR IGNORE`, 새로 들어갔으면 True
- `get_briefing_archive(date: str) -> dict | None` — JSON 컬럼을 파싱해서 반환
- `get_archived_briefing_dates() -> set[str]` — 이미 확정된 날짜 전체
- `get_earliest_mention_date() -> str | None` — `SELECT MIN(date(collected_at)) FROM mentions`
- `get_mentions_by_collected_date(date: str) -> list[dict]` — 채널 필터 없이 그 날짜 전체
  (기존 `get_mentions(channels=...)`는 노출 설정에 종속되므로 이 용도엔 못 씀)

### 2. `news_feed.py` — 콘텐츠 계산

- `competitor_brand_names() -> set`, `market_brand_names() -> set` — 기존 `own_brand_names()`와
  동일한 패턴으로 role 필터만 다르게
- `build_briefing_archive_content(mentions, own_brands, competitor_brands, market_brands, now=None) -> dict`
  — `channel_counts`/`channel_top_news`/`own_brand_news`/`competitor_news`/`market_news`/`total_count`
  키를 가진 dict 반환 (내부적으로 `build_news_items()` 재사용해 점수·카테고리·발췌 계산)
- `archive_pending_briefings() -> list[str]` — 오케스트레이션 함수. 가장 이른 mention 날짜부터
  어제까지, 아직 미확정인 날짜를 찾아 하나씩 `get_mentions_by_collected_date()` →
  `build_briefing_archive_content()` → `db.insert_briefing_archive()`. 새로 확정된 날짜
  리스트를 반환.

### 3. `scheduler.py` — 트리거

- `_tick_archive_briefings()` 추가 (다른 tick과 동일하게 예외를 삼켜서 로그만 남기고
  다른 스케줄에 영향 안 줌). `news_feed.archive_pending_briefings()` 호출, 새로 확정된
  날짜가 있으면 로그. `_tick()`에 추가.
- 다른 스케줄(신규게시물/정책/네이버뉴스/매경/벡터화)처럼 사용자가 HH:MM을 등록하는
  방식이 아니다 — 이건 관리형 하우스키핑 작업이라 항상 켜져 있다.

### 4. `views/briefings.py` — 화면

- 날짜 목록에서 **오늘이 아닌 날짜**를 고르면 `db.get_briefing_archive(date)`로 고정된
  기록을 그대로 렌더링(채널 표시 토글 무관).
- **오늘 날짜**는 지금처럼 실시간 계산 그대로 유지(아직 확정 전이므로 스냅샷이 없음 —
  "오늘은 진행 중" 안내 문구 추가).
- 화면에 섹션 추가: 채널별 수집 현황(표/막대), 채널별 주요 뉴스, 프롭티어 관련 뉴스,
  경쟁사 동향, 시장 동향.
- 만약 오늘 이전 날짜인데 아직 아카이브가 없으면(스케줄러가 아직 못 돈 극히 짧은 시간
  또는 그날 수집 데이터가 아예 없던 경우) "아직 확정 전입니다" 안내로 폴백.

## 테스트

- `db.py`: `insert_briefing_archive` 중복 삽입 시 무시(재생성 불가) 확인, `get_briefing_archive`
  JSON 왕복 확인, `get_earliest_mention_date`/`get_mentions_by_collected_date` 날짜 경계 확인.
- `news_feed.py`: `build_briefing_archive_content`에 브랜드 role 3종 섞인 mentions 픽스처를
  줘서 own/competitor/market 각각 올바르게 분류·top5 제한되는지, 채널별 top3가 점수
  내림차순인지 확인. `archive_pending_briefings`는 이미 확정된 날짜를 재확정하지 않음,
  오늘 날짜는 절대 확정하지 않음, 여러 미확정 날짜를 한 번에 소급 확정함을 확인.
- `scheduler.py`: `_tick_archive_briefings`가 예외를 삼킴, 다른 tick과 독립적으로 동작함을
  기존 tick 테스트 패턴과 동일하게 확인.
- `views/briefings.py`: 기존 관례상 뷰 레이어 자동 테스트 없음 — 로컬 서버로 수동 확인
  (오늘/과거 날짜 전환, 채널 토글 후에도 과거 브리핑 불변 확인).

## 영향받지 않는 부분

- `mentions`/`run_logs` 등 기존 수집 테이블 스키마·로직 — 변경 없음.
- 오늘의 뉴스/뉴스 검색/부동산사 동향/PDF 보고서 — 이 기능들의 채널 표시 토글 동작은
  그대로(실시간 반영 유지). 아카이빙은 "브리핑" 화면에만 적용된다.
- 기존 `news_feed.build_briefings()`/`build_news_items()` 자체는 그대로 두고, 아카이브
  전용 함수를 새로 추가하는 방식이라 다른 화면의 동작에 영향 없음.
