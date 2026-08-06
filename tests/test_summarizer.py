from unittest.mock import MagicMock, patch

import summarizer


def test_summarize_article_returns_empty_string_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr(summarizer, "_load_api_keys", lambda: [])

    assert summarizer.summarize_article("제목", "본문") == ""


def test_summarize_article_returns_empty_string_when_content_is_blank(monkeypatch):
    monkeypatch.setattr(summarizer, "_load_api_keys", lambda: ["key1"])

    assert summarizer.summarize_article("제목", "   ") == ""


def test_summarize_article_returns_gemini_response_text(monkeypatch):
    monkeypatch.setattr(summarizer, "_load_api_keys", lambda: ["key1"])
    fake_response = MagicMock(text="요약된 내용입니다.")
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    with patch.object(summarizer.genai, "Client", return_value=fake_client) as mock_ctor:
        result = summarizer.summarize_article("제목", "본문 내용")

    assert result == "요약된 내용입니다."
    mock_ctor.assert_called_once_with(api_key="key1")


def test_summarize_article_tries_next_key_on_failure(monkeypatch):
    monkeypatch.setattr(summarizer, "_load_api_keys", lambda: ["bad-key", "good-key"])
    fake_response = MagicMock(text="복구된 요약")
    failing_client = MagicMock()
    failing_client.models.generate_content.side_effect = Exception("quota exceeded")
    working_client = MagicMock()
    working_client.models.generate_content.return_value = fake_response

    with patch.object(summarizer.genai, "Client", side_effect=[failing_client, working_client]):
        result = summarizer.summarize_article("제목", "본문 내용")

    assert result == "복구된 요약"


def test_summarize_article_returns_empty_string_when_all_keys_fail(monkeypatch):
    monkeypatch.setattr(summarizer, "_load_api_keys", lambda: ["key1"])
    failing_client = MagicMock()
    failing_client.models.generate_content.side_effect = Exception("boom")

    with patch.object(summarizer.genai, "Client", return_value=failing_client):
        result = summarizer.summarize_article("제목", "본문 내용")

    assert result == ""
