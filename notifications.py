"""
hana_p — 공통 헤더 알림 종(🔔)에 표시할 "새 게시물 등록" 로그를 만든다. 신규 게시물
(브랜드 키워드 4채널 + 네이버뉴스API + 매경API)은 run_logs, 정책 뉴스는 policy_run_logs로
서로 다른 테이블에 쌓이는데, 사용자 입장에서는 "뭐가 새로 들어왔는지" 하나의 목록으로
보고 싶어 해서 두 출처(db.get_run_batches/get_policy_run_batches)를 합쳐 시간순 정렬한다.
"""


def build_notification_entries(mention_batches: list[dict], policy_batches: list[dict]) -> list[dict]:
    """배치별 수집 이력을 알림 항목으로 변환한다. 실제로 새로 저장된 게 없는(inserted=0)
    배치는 스킵한다 — 중복이라 다 걸러진 배치까지 "신규 게시물"이라고 알리면 사용자가
    헷갈린다."""
    entries = []
    for b in mention_batches:
        if b["inserted"] > 0:
            entries.append({
                "ran_at": b["ran_at"],
                "text": f"신규 게시물 {b['inserted']}건 수집 ({b['channels']})",
            })
    for b in policy_batches:
        if b["inserted"] > 0:
            entries.append({
                "ran_at": b["ran_at"],
                "text": f"정책 뉴스 {b['inserted']}건 수집 ({b['sources']})",
            })
    entries.sort(key=lambda e: e["ran_at"], reverse=True)
    return entries


def count_unread(entries: list[dict], last_seen_at: str | None) -> int:
    """last_seen_at 이후에 생긴 항목 수. 세션 최초 진입이라 last_seen_at이 아직 없으면
    지난 이력을 전부 "안 읽음"으로 띄우지 않고 0으로 시작한다."""
    if not last_seen_at:
        return 0
    return sum(1 for e in entries if e["ran_at"] > last_seen_at)
