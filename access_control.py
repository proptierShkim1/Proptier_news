import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
CONFIG_PATH = ROOT / "data" / "access_config.json"

_SUPER_ADMIN_IPS = {
    ip.strip() for ip in os.getenv("SUPER_ADMIN_IPS", "").split(",") if ip.strip()
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"allowed_ips": []}


def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def ip_name_map() -> dict:
    """등록된 IP → 이름 매핑"""
    result = {}
    for entry in load_config().get("allowed_ips", []):
        if isinstance(entry, dict) and entry.get("ip"):
            result[entry["ip"]] = entry.get("name", "")
    return result


def name_for_ip(ip: str) -> str:
    """등록된 이름이 있으면 반환, 없으면 빈 문자열 (설정에 등록 안 된 IP)"""
    return ip_name_map().get(ip, "")


def is_admin(ip: str) -> bool:
    """슈퍼관리자 여부.

    SUPER_ADMIN_IPS(.env)에 등록된 IP는 설정 파일 상태와 무관하게 항상 관리자다 —
    누군가 설정 화면에서 실수로 관리자 체크를 풀어도 잠기지 않도록 하는 안전장치.
    그 외에는 허용 IP 목록이 비어있거나(부트스트랩), 아직 관리자로 지정된 IP가
    하나도 없으면(신규 마이그레이션 직후 잠금 방지) 모두 관리자로 간주.
    """
    if ip and ip in _SUPER_ADMIN_IPS:
        return True
    allowed_ips = load_config().get("allowed_ips", [])
    if not allowed_ips:
        return True
    if not any(isinstance(e, dict) and e.get("is_admin") for e in allowed_ips):
        return True
    if not ip:
        return False
    return any(
        isinstance(e, dict) and e.get("ip") == ip and e.get("is_admin")
        for e in allowed_ips
    )
