"""
hana_p — 데이터 수집 공용 유틸리티 (키워드/스케줄 설정, 상대 날짜 변환)
"""

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
KEYWORDS_FILE = DATA_DIR / "keywords.json"
COLLECTION_SCHEDULE_FILE = DATA_DIR / "collection_schedule.json"
POLICY_COLLECTION_SCHEDULE_FILE = DATA_DIR / "policy_collection_schedule.json"
NAVER_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR / "naver_news_collection_schedule.json"
VECTOR_COLLECTION_SCHEDULE_FILE = DATA_DIR / "vector_collection_schedule.json"
CHANNEL_VISIBILITY_FILE = DATA_DIR / "channel_visibility.json"
AGENT_CHAT_HISTORY_FILE = DATA_DIR / "agent_chat_history.json"
ALL_MENTION_CHANNELS = ["네이버", "구글", "다음", "커뮤니티", "네이버뉴스API"]


def escape_html(text: str) -> str:
    """크롤링한(신뢰할 수 없는) 텍스트를 HTML 본문/속성에 넣기 전에 이스케이프한다.
    `&`를 가장 먼저 치환해야 뒤이어 만든 `&lt;` 등의 엔티티가 다시 이스케이프되지 않는다."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_keywords() -> dict:
    cfg = load_json(KEYWORDS_FILE, {"brands": [], "context": [], "exclude": []})
    cfg.setdefault("brands", [])
    cfg.setdefault("context", [])
    cfg.setdefault("exclude", [])
    return cfg


def save_keywords(cfg: dict) -> None:
    save_json(KEYWORDS_FILE, cfg)


def _normalize_schedule_times(times: list) -> list:
    normalized = []
    for entry in times:
        if isinstance(entry, dict):
            if not entry.get("enabled", True):
                continue
            time_str = entry.get("time", "")
        else:
            time_str = entry
        if time_str and time_str not in normalized:
            normalized.append(time_str)
    return normalized


def load_collection_schedule() -> dict:
    cfg = load_json(COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_collection_schedule(cfg: dict) -> None:
    save_json(COLLECTION_SCHEDULE_FILE, cfg)


def load_policy_collection_schedule() -> dict:
    cfg = load_json(POLICY_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_policy_collection_schedule(cfg: dict) -> None:
    save_json(POLICY_COLLECTION_SCHEDULE_FILE, cfg)


def load_naver_news_collection_schedule() -> dict:
    cfg = load_json(NAVER_NEWS_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_naver_news_collection_schedule(cfg: dict) -> None:
    save_json(NAVER_NEWS_COLLECTION_SCHEDULE_FILE, cfg)


def load_vector_collection_schedule() -> dict:
    cfg = load_json(VECTOR_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_vector_collection_schedule(cfg: dict) -> None:
    save_json(VECTOR_COLLECTION_SCHEDULE_FILE, cfg)


def load_channel_visibility() -> list:
    """오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서 5개 화면에 표시할
    채널 목록. 파일이 없으면 전체 채널이 기본값이다."""
    cfg = load_json(CHANNEL_VISIBILITY_FILE, {"enabled_channels": list(ALL_MENTION_CHANNELS)})
    return [c for c in cfg.get("enabled_channels", []) if c in ALL_MENTION_CHANNELS]


def save_channel_visibility(channels: list) -> None:
    save_json(CHANNEL_VISIBILITY_FILE, {"enabled_channels": channels})


def load_agent_chat_sessions(ip: str) -> list:
    """AI AGENT 채팅 기록을 접속 IP 기준으로 불러온다 — F5 새로고침이나 다른 탭 이동 시에도
    대화가 유지되도록 session_state가 아니라 파일에 저장한다. IP 기반 접근 제어를 쓰는
    이 앱의 기존 사용자 식별 방식과 동일하게 IP를 키로 쓴다.

    반환값은 [{"started_at": "...", "messages": [{"role", "content"}, ...]}, ...] 형태로,
    오래된 대화부터 순서대로 담겨 있다 — 마지막 항목이 진행 중인(가장 최근) 대화다. 사용자가
    "대화 초기화"를 누르면 기존 대화는 지우지 않고 새 항목을 추가해서, 지난 대화를 나중에도
    볼 수 있게 한다."""
    if not ip:
        return []
    all_sessions = load_json(AGENT_CHAT_HISTORY_FILE, {})
    raw = all_sessions.get(ip, [])
    if raw and isinstance(raw[0], dict) and "role" in raw[0]:
        # 세션 단위로 나누기 전(초기 버전)에 저장된, 메시지 리스트 그대로인 옛 형식 — 진행 중인
        # 대화 하나로 취급해 마이그레이션한다.
        return [{"started_at": "", "messages": raw}]
    return raw


_agent_chat_history_lock = threading.Lock()


def save_agent_chat_sessions(ip: str, sessions: list) -> None:
    """read-entire-file → mutate → write-entire-file 방식이라, 서로 다른 IP가 거의 동시에
    저장하면 락 없이는 한쪽의 저장이 다른 쪽 것을 덮어써 유실될 수 있다 — 파일 전체를 다루는
    임계구역을 프로세스 전역 락으로 감싸 직렬화한다."""
    if not ip:
        return
    with _agent_chat_history_lock:
        all_sessions = load_json(AGENT_CHAT_HISTORY_FILE, {})
        all_sessions[ip] = sessions
        save_json(AGENT_CHAT_HISTORY_FILE, all_sessions)


_RELATIVE_KOREAN_DATE_RE = re.compile(r"^(\d+)(분|시간|일)\s*전$")
_RELATIVE_UNIT_TO_KWARG = {"분": "minutes", "시간": "hours", "일": "days"}


def resolve_relative_korean_date(text: str, now: datetime) -> str | None:
    """'N분/시간/일 전' 형식의 상대 시각 문자열을 now 기준 절대 날짜("YYYY.MM.DD")로
    변환한다. 상대 시각 패턴이 아니면 None을 반환한다."""
    match = _RELATIVE_KOREAN_DATE_RE.match(text)
    if not match:
        return None
    amount, unit = match.groups()
    age = timedelta(**{_RELATIVE_UNIT_TO_KWARG[unit]: int(amount)})
    return (now - age).strftime("%Y.%m.%d")
