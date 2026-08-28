"""
hana_p — 데이터 수집 공용 유틸리티 (키워드/스케줄 설정, 상대 날짜 변환)
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
KEYWORDS_FILE = DATA_DIR / "keywords.json"
COLLECTION_SCHEDULE_FILE = DATA_DIR / "collection_schedule.json"
POLICY_COLLECTION_SCHEDULE_FILE = DATA_DIR / "policy_collection_schedule.json"
NAVER_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR / "naver_news_collection_schedule.json"
MK_NEWS_COLLECTION_SCHEDULE_FILE = DATA_DIR / "mk_news_collection_schedule.json"
VECTOR_COLLECTION_SCHEDULE_FILE = DATA_DIR / "vector_collection_schedule.json"
CHANNEL_VISIBILITY_FILE = DATA_DIR / "channel_visibility.json"
AGENT_SETTINGS_FILE = DATA_DIR / "agent_settings.json"
WEBHOOKS_FILE = DATA_DIR / "webhooks.json"
WEBHOOK_SCHEDULE_FILE = DATA_DIR / "webhook_schedule.json"
ALL_MENTION_CHANNELS = ["네이버", "구글", "다음", "커뮤니티", "네이버뉴스API", "매경API"]


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


def load_mk_news_collection_schedule() -> dict:
    cfg = load_json(MK_NEWS_COLLECTION_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_mk_news_collection_schedule(cfg: dict) -> None:
    save_json(MK_NEWS_COLLECTION_SCHEDULE_FILE, cfg)


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


def load_agent_settings() -> dict:
    """AI AGENT 페이지 동작을 조정하는 관리자 설정. always_show_hybrid_search가 True면
    사내 데이터가 충분하다고 판단된 답변에도 Hybrid Search 버튼을 계속 보여준다 — 벡터
    검색이 무관한 자료를 "관련 있음"으로 잘못 판단한 경우(수집 키워드가 넓어 생기는 노이즈
    등)에도 사용자가 직접 웹 검색 답변을 추가로 받아볼 수 있게 하기 위함."""
    cfg = load_json(AGENT_SETTINGS_FILE, {"always_show_hybrid_search": False})
    cfg.setdefault("always_show_hybrid_search", False)
    return cfg


def save_agent_settings(cfg: dict) -> None:
    save_json(AGENT_SETTINGS_FILE, cfg)


def load_webhooks() -> list[dict]:
    return load_json(WEBHOOKS_FILE, [])


def save_webhooks(webhooks: list[dict]) -> None:
    save_json(WEBHOOKS_FILE, webhooks)


def add_webhook(name: str, url: str) -> dict:
    webhooks = load_webhooks()
    entry = {"id": uuid.uuid4().hex, "name": name, "url": url, "enabled": True}
    webhooks.append(entry)
    save_webhooks(webhooks)
    return entry


def delete_webhook(webhook_id: str) -> None:
    save_webhooks([w for w in load_webhooks() if w["id"] != webhook_id])


def set_webhook_enabled(webhook_id: str, enabled: bool) -> None:
    webhooks = load_webhooks()
    for w in webhooks:
        if w["id"] == webhook_id:
            w["enabled"] = enabled
    save_webhooks(webhooks)


def load_webhook_schedule() -> dict:
    cfg = load_json(WEBHOOK_SCHEDULE_FILE, {"times": []})
    cfg["times"] = _normalize_schedule_times(cfg.get("times", []))
    return cfg


def save_webhook_schedule(cfg: dict) -> None:
    save_json(WEBHOOK_SCHEDULE_FILE, cfg)


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
