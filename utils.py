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
