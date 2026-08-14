"""
hana_p — Gemini 임베딩으로 mentions/policy_events를 벡터화해 DB(mentions.embedding/
policy_events.embedding, JSON)와 sqlite-vec 색인(mention_vectors/policy_vectors, vec0
가상 테이블)에 함께 저장한다. summarizer.py와 같은 .env(GEMINI_API_KEYS, 여러 키 순차
failover)를 재사용한다.

search_similar_mentions()/search_similar_policy_events()로 질의 텍스트와 가장 가까운
문서를 코사인 거리 기반으로 찾아 AI AGENT(agent_chat.py)의 답변 그라운딩에 쓴다.
"""

import json
import os
import random
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
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    random.shuffle(keys)
    return keys


def has_api_keys() -> bool:
    return bool(_load_api_keys())


def embed_text(text: str) -> list[float] | None:
    """text를 Gemini로 임베딩해 실수 리스트로 반환한다. 키가 없거나 텍스트가 비었거나
    모든 키 호출이 실패하면 None을 반환한다. 임베딩 API 응답은 토큰 사용량을 안 주므로
    (usage_metadata 없음), 호출 성공/실패 건수만 api_usage_log에 남긴다."""
    text = (text or "").strip()
    keys = _load_api_keys()
    if not keys or not text:
        return None
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.embed_content(model=_EMBEDDING_MODEL, contents=text)
            db.insert_api_usage("vectorizer", _EMBEDDING_MODEL, ok=True)
            return list(response.embeddings[0].values)
        except Exception:
            db.insert_api_usage("vectorizer", _EMBEDDING_MODEL, ok=False)
            continue
    return None


_progress_lock = threading.Lock()
_progress: dict[str, dict] = {}


def _set_progress(run_id: str, source: str, done: int, total: int) -> None:
    """run_id별 진행 상황을 소스(mentions/policy_events) 단위로 기록한다. 배치 하나가
    최대 200건까지 순차로 Gemini를 호출해서 꽤 걸릴 수 있는데, 이전에는 각 소스가 전부
    끝나야만 vector_run_logs에 1행이 쌓여서 그 사이엔 진행률을 알 수 없었다 — 매 건마다
    갱신해서 UI가 실시간으로 몇 건째인지 보여줄 수 있게 한다."""
    with _progress_lock:
        _progress.setdefault(run_id, {})[source] = {"done": done, "total": total}


def get_vectorize_progress(run_id: str) -> dict:
    with _progress_lock:
        return {k: dict(v) for k, v in _progress.get(run_id, {}).items()}


def _vectorize_mentions(limit: int, trigger: str, run_id: str) -> dict:
    pending = db.get_mentions_without_embedding(limit)
    total = len(pending)
    inserted = skipped = 0
    for i, row in enumerate(pending, start=1):
        text = f"{row['title']}\n{row.get('content') or row.get('snippet') or ''}".strip()
        vector = embed_text(text)
        if vector:
            db.update_mention_embedding(row["id"], json.dumps(vector))
            db.upsert_mention_vector(row["id"], vector)
            inserted += 1
        else:
            skipped += 1
        _set_progress(run_id, "mentions", i, total)
    result = {"fetched": total, "inserted": inserted, "skipped": skipped}
    db.insert_vector_run_log({
        "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger,
        "source": "mentions", "ok": 1 if skipped == 0 else 0,
        "message": "" if skipped == 0 else f"{skipped}건 임베딩 실패", "run_id": run_id,
        **result,
    })
    return result


def _vectorize_policy_events(limit: int, trigger: str, run_id: str) -> dict:
    pending = db.get_policy_events_without_embedding(limit)
    total = len(pending)
    inserted = skipped = 0
    for i, row in enumerate(pending, start=1):
        text = f"{row['title']}\n{row.get('department', '')}".strip()
        vector = embed_text(text)
        if vector:
            db.update_policy_event_embedding(row["id"], json.dumps(vector))
            db.upsert_policy_vector(row["id"], vector)
            inserted += 1
        else:
            skipped += 1
        _set_progress(run_id, "policy_events", i, total)
    result = {"fetched": total, "inserted": inserted, "skipped": skipped}
    db.insert_vector_run_log({
        "ran_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "trigger": trigger,
        "source": "policy_events", "ok": 1 if skipped == 0 else 0,
        "message": "" if skipped == 0 else f"{skipped}건 임베딩 실패", "run_id": run_id,
        **result,
    })
    return result


def sync_vector_index() -> dict:
    """mentions.embedding/policy_events.embedding에는 있지만 아직 sqlite-vec 색인
    (mention_vectors/policy_vectors)에는 없는 행을 채운다 — 색인 테이블이 나중에
    추가되었거나 색인이 유실된 경우를 복구하는 용도. vectorize_pending()이 매 실행마다
    호출해서, 새로 벡터화한 건 외에 과거에 남아있던 누락분도 함께 메운다."""
    mention_rows = db.get_mentions_missing_vector_index()
    for row in mention_rows:
        db.upsert_mention_vector(row["id"], json.loads(row["embedding"]))
    policy_rows = db.get_policy_events_missing_vector_index()
    for row in policy_rows:
        db.upsert_policy_vector(row["id"], json.loads(row["embedding"]))
    return {"mentions": len(mention_rows), "policy_events": len(policy_rows)}


def vectorize_pending(
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE, trigger: str = "수동", run_id: str | None = None,
) -> dict:
    """아직 embedding이 없는 mentions/policy_events를 최대 limit_per_source건씩 벡터화하고,
    sqlite-vec 색인에도 함께 반영한다(sync_vector_index로 과거 누락분까지 정리). 두 소스를
    같은 run_id로 기록해 벡터화 이력에서 1세트로 묶인다."""
    run_id = run_id or str(uuid.uuid4())[:8]
    mentions_result = _vectorize_mentions(limit_per_source, trigger, run_id)
    policy_result = _vectorize_policy_events(limit_per_source, trigger, run_id)
    sync_vector_index()
    return {"run_id": run_id, "mentions": mentions_result, "policy_events": policy_result}


def search_similar_mentions(query_text: str, top_k: int = 5) -> list[dict]:
    """질의 텍스트를 임베딩해 가장 유사한 mentions 상위 top_k건을 반환한다. 임베딩 실패나
    색인이 비어있으면 빈 리스트를 반환한다(예외를 던지지 않음 — AI AGENT는 그라운딩 없이
    일반 대화로 계속 답할 수 있어야 한다)."""
    vector = embed_text(query_text)
    if not vector:
        return []
    return db.search_mention_vectors(vector, top_k=top_k)


def search_similar_policy_events(query_text: str, top_k: int = 5) -> list[dict]:
    vector = embed_text(query_text)
    if not vector:
        return []
    return db.search_policy_vectors(vector, top_k=top_k)


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
