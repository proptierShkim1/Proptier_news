from unittest.mock import MagicMock, patch

import vectorizer


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


def test_vectorize_pending_embeds_mentions_and_policy_events_separately():
    mentions_pending = [{"id": 1, "title": "제목1", "content": "본문1", "snippet": ""}]
    policy_pending = [{"id": 2, "title": "제목2", "department": "국토부"}]

    with patch("db.get_mentions_without_embedding", return_value=mentions_pending), \
         patch("db.get_policy_events_without_embedding", return_value=policy_pending), \
         patch.object(vectorizer, "embed_text", return_value=[0.1, 0.2]) as mock_embed, \
         patch("db.update_mention_embedding") as mock_update_mention, \
         patch("db.update_policy_event_embedding") as mock_update_policy, \
         patch("db.insert_vector_run_log") as mock_log:
        result = vectorizer.vectorize_pending(run_id="fixed-run")

    assert mock_embed.call_count == 2
    mock_update_mention.assert_called_once_with(1, "[0.1, 0.2]")
    mock_update_policy.assert_called_once_with(2, "[0.1, 0.2]")
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
         patch("db.insert_vector_run_log"):
        result = vectorizer.vectorize_pending(run_id="fixed-run")

    mock_update_mention.assert_not_called()
    assert result["mentions"] == {"fetched": 1, "inserted": 0, "skipped": 1}


def test_start_background_vectorize_returns_none_when_already_running(monkeypatch):
    monkeypatch.setattr(vectorizer, "_active_run_id", "already-running")

    assert vectorizer.start_background_vectorize() is None

    monkeypatch.setattr(vectorizer, "_active_run_id", None)


def test_active_vectorize_run_id_reflects_module_state(monkeypatch):
    monkeypatch.setattr(vectorizer, "_active_run_id", "run-123")

    assert vectorizer.active_vectorize_run_id() == "run-123"
