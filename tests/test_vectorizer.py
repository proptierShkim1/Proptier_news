from unittest.mock import MagicMock, patch

import pytest

import vectorizer


@pytest.fixture(autouse=True)
def _stub_api_usage_logging(monkeypatch):
    """embed_text가 이제 매 호출마다 db.insert_api_usage를 남긴다 — 로깅 자체를 검증하는
    테스트를 빼고는 기본적으로 no-op 처리해 진짜 DB를 건드리지 않게 한다."""
    monkeypatch.setattr(vectorizer.db, "insert_api_usage", lambda *a, **kw: None)


def test_has_api_keys_false_when_none_configured(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: [])

    assert vectorizer.has_api_keys() is False


def test_has_api_keys_true_when_configured(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])

    assert vectorizer.has_api_keys() is True


def test_embed_text_returns_none_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: [])

    assert vectorizer.embed_text("텍스트") is None


def test_embed_text_returns_none_when_text_is_blank(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])

    assert vectorizer.embed_text("   ") is None


def test_embed_text_returns_gemini_embedding_values(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])
    fake_embedding = MagicMock(values=[0.1, 0.2, 0.3])
    fake_response = MagicMock(embeddings=[fake_embedding])
    fake_client = MagicMock()
    fake_client.models.embed_content.return_value = fake_response

    with patch.object(vectorizer.genai, "Client", return_value=fake_client) as mock_ctor:
        result = vectorizer.embed_text("텍스트")

    assert result == [0.1, 0.2, 0.3]
    mock_ctor.assert_called_once_with(api_key="key1")


def test_embed_text_tries_next_key_on_failure(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["bad-key", "good-key"])
    fake_embedding = MagicMock(values=[0.5])
    fake_response = MagicMock(embeddings=[fake_embedding])
    failing_client = MagicMock()
    failing_client.models.embed_content.side_effect = Exception("quota exceeded")
    working_client = MagicMock()
    working_client.models.embed_content.return_value = fake_response

    with patch.object(vectorizer.genai, "Client", side_effect=[failing_client, working_client]):
        result = vectorizer.embed_text("텍스트")

    assert result == [0.5]


def test_embed_text_returns_none_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.models.embed_content.side_effect = Exception("boom")

    with patch.object(vectorizer.genai, "Client", return_value=failing_client):
        result = vectorizer.embed_text("텍스트")

    assert result is None


def test_embed_text_logs_api_usage_on_success(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])
    fake_embedding = MagicMock(values=[0.1, 0.2, 0.3])
    fake_response = MagicMock(embeddings=[fake_embedding])
    fake_client = MagicMock()
    fake_client.models.embed_content.return_value = fake_response

    with patch.object(vectorizer.genai, "Client", return_value=fake_client), \
         patch.object(vectorizer.db, "insert_api_usage") as mock_usage:
        vectorizer.embed_text("텍스트")

    mock_usage.assert_called_once_with("vectorizer", vectorizer._EMBEDDING_MODEL, ok=True)


def test_embed_text_logs_api_usage_as_failed_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(vectorizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.models.embed_content.side_effect = Exception("boom")

    with patch.object(vectorizer.genai, "Client", return_value=failing_client), \
         patch.object(vectorizer.db, "insert_api_usage") as mock_usage:
        vectorizer.embed_text("텍스트")

    mock_usage.assert_called_once_with("vectorizer", vectorizer._EMBEDDING_MODEL, ok=False)


def test_vectorize_pending_embeds_mentions_and_policy_events_separately():
    mentions_pending = [{"id": 1, "title": "제목1", "content": "본문1", "snippet": ""}]
    policy_pending = [{"id": 2, "title": "제목2", "department": "국토부"}]

    with patch("db.get_mentions_without_embedding", return_value=mentions_pending), \
         patch("db.get_policy_events_without_embedding", return_value=policy_pending), \
         patch.object(vectorizer, "embed_text", return_value=[0.1, 0.2]) as mock_embed, \
         patch("db.update_mention_embedding") as mock_update_mention, \
         patch("db.update_policy_event_embedding") as mock_update_policy, \
         patch("db.upsert_mention_vector") as mock_upsert_mention, \
         patch("db.upsert_policy_vector") as mock_upsert_policy, \
         patch("db.get_mentions_missing_vector_index", return_value=[]), \
         patch("db.get_policy_events_missing_vector_index", return_value=[]), \
         patch("db.insert_vector_run_log") as mock_log:
        result = vectorizer.vectorize_pending(run_id="fixed-run")

    assert mock_embed.call_count == 2
    mock_update_mention.assert_called_once_with(1, "[0.1, 0.2]")
    mock_update_policy.assert_called_once_with(2, "[0.1, 0.2]")
    mock_upsert_mention.assert_called_once_with(1, [0.1, 0.2])
    mock_upsert_policy.assert_called_once_with(2, [0.1, 0.2])
    assert result["run_id"] == "fixed-run"
    assert result["mentions"] == {"fetched": 1, "inserted": 1, "skipped": 0}
    assert result["policy_events"] == {"fetched": 1, "inserted": 1, "skipped": 0}
    assert mock_log.call_count == 2


def test_vectorize_pending_counts_failed_embeddings_as_skipped():
    mentions_pending = [{"id": 1, "title": "제목1", "content": "본문1", "snippet": ""}]

    with patch("db.get_mentions_without_embedding", return_value=mentions_pending), \
         patch("db.get_policy_events_without_embedding", return_value=[]), \
         patch.object(vectorizer, "embed_text", return_value=None), \
         patch("db.update_mention_embedding") as mock_update_mention, \
         patch("db.upsert_mention_vector") as mock_upsert_mention, \
         patch("db.get_mentions_missing_vector_index", return_value=[]), \
         patch("db.get_policy_events_missing_vector_index", return_value=[]), \
         patch("db.insert_vector_run_log"):
        result = vectorizer.vectorize_pending(run_id="fixed-run")

    mock_update_mention.assert_not_called()
    mock_upsert_mention.assert_not_called()
    assert result["mentions"] == {"fetched": 1, "inserted": 0, "skipped": 1}


def test_sync_vector_index_backfills_mentions_and_policy_events_missing_from_index():
    with patch("db.get_mentions_missing_vector_index", return_value=[{"id": 1, "embedding": "[0.1, 0.2]"}]) as mock_get_mentions, \
         patch("db.get_policy_events_missing_vector_index", return_value=[{"id": 2, "embedding": "[0.3, 0.4]"}]) as mock_get_policy, \
         patch("db.upsert_mention_vectors_batch") as mock_upsert_mention, \
         patch("db.upsert_policy_vectors_batch") as mock_upsert_policy:
        result = vectorizer.sync_vector_index()

    mock_get_mentions.assert_called_once_with(limit=vectorizer._FULL_REINDEX_LIMIT)
    mock_get_policy.assert_called_once_with(limit=vectorizer._FULL_REINDEX_LIMIT)
    mock_upsert_mention.assert_called_once_with([(1, [0.1, 0.2])])
    mock_upsert_policy.assert_called_once_with([(2, [0.3, 0.4])])
    assert result == {"mentions": 1, "policy_events": 1}


def test_sync_vector_index_clears_and_skips_rows_with_unparseable_embedding():
    """DB 복구 과정에서 embedding 컬럼에 JSON이 아닌 값(엉뚱한 텍스트 등)이 들어간
    경우 sync_vector_index 전체가 죽지 않고, 그 행만 벡터화 대기 상태로 되돌려야 한다."""
    mention_rows = [{"id": 1, "embedding": "[0.1, 0.2]"}, {"id": 2, "embedding": "깨진 텍스트"}]
    policy_rows = [{"id": 3, "embedding": "not json"}]
    with patch("db.get_mentions_missing_vector_index", return_value=mention_rows), \
         patch("db.get_policy_events_missing_vector_index", return_value=policy_rows), \
         patch("db.upsert_mention_vectors_batch") as mock_upsert_mention, \
         patch("db.upsert_policy_vectors_batch") as mock_upsert_policy, \
         patch("db.clear_mention_embeddings") as mock_clear_mention, \
         patch("db.clear_policy_event_embeddings") as mock_clear_policy:
        result = vectorizer.sync_vector_index()

    mock_upsert_mention.assert_called_once_with([(1, [0.1, 0.2])])
    mock_upsert_policy.assert_called_once_with([])
    mock_clear_mention.assert_called_once_with([2])
    mock_clear_policy.assert_called_once_with([3])
    assert result == {"mentions": 1, "policy_events": 0}


def test_export_vector_backup_bundles_mentions_and_policy_events():
    with patch("db.get_mention_embeddings_for_backup", return_value=[{"url": "u1", "embedding": "[0.1]"}]), \
         patch("db.get_policy_event_embeddings_for_backup", return_value=[{"url": "u2", "embedding": "[0.2]"}]):
        backup = vectorizer.export_vector_backup()

    assert backup["mentions"] == [{"url": "u1", "embedding": "[0.1]"}]
    assert backup["policy_events"] == [{"url": "u2", "embedding": "[0.2]"}]
    assert "created_at" in backup


def test_search_similar_mentions_returns_empty_list_when_embedding_fails():
    with patch.object(vectorizer, "embed_text", return_value=None):
        assert vectorizer.search_similar_mentions("질문") == []


def test_search_similar_mentions_delegates_to_db_search():
    with patch.object(vectorizer, "embed_text", return_value=[0.1, 0.2]), \
         patch("db.search_mention_vectors", return_value=[{"id": 1, "title": "제목"}]) as mock_search:
        result = vectorizer.search_similar_mentions("질문", top_k=3)

    mock_search.assert_called_once_with([0.1, 0.2], top_k=3)
    assert result == [{"id": 1, "title": "제목"}]


def test_search_similar_policy_events_returns_empty_list_when_embedding_fails():
    with patch.object(vectorizer, "embed_text", return_value=None):
        assert vectorizer.search_similar_policy_events("질문") == []


def test_search_similar_policy_events_delegates_to_db_search():
    with patch.object(vectorizer, "embed_text", return_value=[0.1, 0.2]), \
         patch("db.search_policy_vectors", return_value=[{"id": 2, "title": "정책"}]) as mock_search:
        result = vectorizer.search_similar_policy_events("질문", top_k=3)

    mock_search.assert_called_once_with([0.1, 0.2], top_k=3)
    assert result == [{"id": 2, "title": "정책"}]


def test_start_background_vectorize_returns_none_when_already_running(monkeypatch):
    monkeypatch.setattr(vectorizer, "_active_run_id", "already-running")

    assert vectorizer.start_background_vectorize() is None

    monkeypatch.setattr(vectorizer, "_active_run_id", None)


def test_active_vectorize_run_id_reflects_module_state(monkeypatch):
    monkeypatch.setattr(vectorizer, "_active_run_id", "run-123")

    assert vectorizer.active_vectorize_run_id() == "run-123"


def test_get_vectorize_progress_returns_empty_dict_for_unknown_run_id():
    assert vectorizer.get_vectorize_progress("unknown-run") == {}


def test_vectorize_mentions_updates_progress_incrementally():
    mentions_pending = [
        {"id": 1, "title": "제목1", "content": "본문1", "snippet": ""},
        {"id": 2, "title": "제목2", "content": "본문2", "snippet": ""},
    ]
    seen_progress = []

    def fake_embed(text):
        seen_progress.append(vectorizer.get_vectorize_progress("run-x").get("mentions"))
        return [0.1, 0.2]

    with patch("db.get_mentions_without_embedding", return_value=mentions_pending), \
         patch.object(vectorizer, "embed_text", side_effect=fake_embed), \
         patch("db.update_mention_embedding"), patch("db.upsert_mention_vector"), \
         patch("db.insert_vector_run_log"):
        vectorizer._vectorize_mentions(limit=10, trigger="수동", run_id="run-x")

    # 첫 번째 항목을 임베딩하기 시작할 때는 아직 이전 건의 진행 갱신이 없었어야 하고,
    # 두 번째 항목을 시작할 때는 1/2까지 갱신되어 있어야 한다(매 건 처리 후 갱신).
    assert seen_progress == [None, {"done": 1, "total": 2}]
    assert vectorizer.get_vectorize_progress("run-x") == {"mentions": {"done": 2, "total": 2}}


def test_load_api_keys_returns_all_keys_regardless_of_order(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3")

    result = vectorizer._load_api_keys()

    assert sorted(result) == ["key1", "key2", "key3"]


def test_load_api_keys_shuffles_order_across_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key1,key2,key3,key4,key5,key6,key7,key8")

    orders = {tuple(vectorizer._load_api_keys()) for _ in range(20)}

    assert len(orders) > 1
