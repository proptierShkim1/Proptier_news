"""
hana_p — Gemini 임베딩으로 mentions/policy_events를 벡터화해 DB에 저장.
summarizer.py와 같은 .env(GEMINI_API_KEYS, 여러 키 순차 failover)를 재사용한다.
임베딩 자체를 이용한 검색(코사인 유사도 등)은 이후 AI AGENT 연동 시 추가될 예정이고,
여기서는 벡터를 만들어 저장하는 것까지만 다룬다.
"""

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai

import db

load_dotenv(Path(__file__).resolve().parent / ".env")

_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_LIMIT_PER_SOURCE = 200


def _load_api_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def has_api_keys() -> bool:
    return bool(_load_api_keys())


def embed_text(text: str) -> list[float] | None:
    """text를 Gemini로 임베딩해 실수 리스트로 반환한다. 키가 없거나 텍스트가 비었거나
    모든 키 호출이 실패하면 None을 반환한다."""
    text = (text or "").strip()
    keys = _load_api_keys()
    if not keys or not text:
        return None
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.embed_content(model=_EMBEDDING_MODEL, contents=text)
            return list(response.embeddings[0].values)
        except Exception:
            continue
    return None


def _vectorize_mentions(limit: int, trigger: str, run_id: str) -> dict:
    pending = db.get_mentions_without_embedding(limit)
    inserted = skipped = 0
    for row in pending:
        text = f"{row['title']}\n{row.get('content') or row.get('snippet') or ''}".strip()
        vector = embed_text(text)
        if vector:
            db.update_mention_embedding(row["id"], json.dumps(vector))
            inserted += 1
        else:
            skipped += 1
    result = {"fetched": len(pending), "inserted": inserted, "skipped": skipped}
    db.insert_vector_run_log({
        "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger,
        "source": "mentions", "ok": 1 if skipped == 0 else 0,
        "message": "" if skipped == 0 else f"{skipped}건 임베딩 실패", "run_id": run_id,
        **result,
    })
    return result


def _vectorize_policy_events(limit: int, trigger: str, run_id: str) -> dict:
    pending = db.get_policy_events_without_embedding(limit)
    inserted = skipped = 0
    for row in pending:
        text = f"{row['title']}\n{row.get('department', '')}".strip()
        vector = embed_text(text)
        if vector:
            db.update_policy_event_embedding(row["id"], json.dumps(vector))
            inserted += 1
        else:
            skipped += 1
    result = {"fetched": len(pending), "inserted": inserted, "skipped": skipped}
    db.insert_vector_run_log({
        "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger,
        "source": "policy_events", "ok": 1 if skipped == 0 else 0,
        "message": "" if skipped == 0 else f"{skipped}건 임베딩 실패", "run_id": run_id,
        **result,
    })
    return result


def vectorize_pending(
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """아직 embedding이 없는 mentions/policy_events를 최대 limit_per_source건씩 벡터화한다.
    두 소스를 같은 run_id로 기록해 벡터화 이력에서 1세트로 묶인다."""
    run_id = run_id or str(uuid.uuid4())[:8]
    mentions_result = _vectorize_mentions(limit_per_source, trigger, run_id)
    policy_result = _vectorize_policy_events(limit_per_source, trigger, run_id)
    return {"run_id": run_id, "mentions": mentions_result, "policy_events": policy_result}


_state_lock = threading.Lock()
_active_run_id: str | None = None


def active_vectorize_run_id() -> str | None:
    with _state_lock:
        return _active_run_id


def start_background_vectorize(
    trigger: str = "수동", limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
) -> str | None:
    """이미 진행 중인 벡터화가 없으면 데몬 스레드로 시작하고 run_id를 반환한다."""
    global _active_run_id
    with _state_lock:
        if _active_run_id is not None:
            return None
        run_id = str(uuid.uuid4())[:8]
        _active_run_id = run_id

    def _worker():
        global _active_run_id
        try:
            vectorize_pending(limit_per_source=limit_per_source, trigger=trigger, run_id=run_id)
        finally:
            with _state_lock:
                _active_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id
