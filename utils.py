"""
hana_p — 데이터 수집 공용 유틸리티 (키워드/스케줄 설정, 상대 날짜 변환)
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
KEYWORDS_FILE = DATA_DIR / "keywords.json"
COLLECTION_SCHEDULE_FILE = DATA_DIR / "collection_schedule.json"
POLICY_COLLECTION_SCHEDULE_FILE = DATA_DIR / "policy_collection_schedule.json"
NAVER_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR / "naver_news_collection_schedule.json"
CHANNEL_VISIBILITY_FILE = DATA_DIR / "channel_visibility.json"
AGENT_CHAT_HISTORY_FILE = DATA_DIR / "agent_chat_history.json"
ALL_MENTION_CHANNELS = ["네이버", "구글", "다음", "커뮤니티", "네이버뉴스API"]


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


def load_channel_visibility() -> list:
    """오늘의 뉴스/부동산사 동향/브리핑/뉴스 검색/PDF 보고서 5개 화면에 표시할
    채널 목록. 파일이 없으면 전체 채널이 기본값이다."""
    cfg = load_json(CHANNEL_VISIBILITY_FILE, {"enabled_channels": list(ALL_MENTION_CHANNELS)})
    return [c for c in cfg.get("enabled_channels", []) if c in ALL_MENTION_CHANNELS]


def save_channel_visibility(channels: list) -> None:
    save_json(CHANNEL_VISIBILITY_FILE, {"enabled_channels": channels})


def load_agent_chat_history(ip: str) -> list:
    """AI AGENT 채팅 기록을 접속 IP 기준으로 불러온다 — F5 새로고침이나 다른 탭 이동 시에도
    대화가 유지되도록 session_state가 아니라 파일에 저장한다. IP 기반 접근 제어를 쓰는
    이 앱의 기존 사용자 식별 방식과 동일하게 IP를 키로 쓴다."""
    all_histories = load_json(AGENT_CHAT_HISTORY_FILE, {})
    return all_histories.get(ip, []) if ip else []


def save_agent_chat_history(ip: str, history: list) -> None:
    if not ip:
        return
    all_histories = load_json(AGENT_CHAT_HISTORY_FILE, {})
    all_histories[ip] = history
    save_json(AGENT_CHAT_HISTORY_FILE, all_histories)


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
