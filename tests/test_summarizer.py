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


def _item(title="제목", content="", summary="", mention_id=1):
    return {"title": title, "content": content, "summary": summary, "mention_id": mention_id,
            "desc_long": ["긴 발췌"]}


def test_ensure_pdf_summaries_calls_gemini_only_for_items_with_content_and_no_summary():
    items = [_item(content="원문 있음", summary="")]

    with patch.object(summarizer, "summarize_article", return_value="새 AI 요약") as mock_summarize, \
         patch("db.update_mention_summary") as mock_update:
        updated = summarizer.ensure_pdf_summaries(items)

    mock_summarize.assert_called_once_with("제목", "원문 있음")
    mock_update.assert_called_once_with(1, "새 AI 요약")
    assert updated is True
    assert items[0]["summary"] == "새 AI 요약"
    assert items[0]["desc_long"] == ["새 AI 요약"]


def test_ensure_pdf_summaries_skips_items_that_already_have_a_summary():
    items = [_item(content="원문 있음", summary="이미 있는 요약")]

    with patch.object(summarizer, "summarize_article") as mock_summarize:
        updated = summarizer.ensure_pdf_summaries(items)

    mock_summarize.assert_not_called()
    assert updated is False
    assert items[0]["desc_long"] == ["긴 발췌"]


def test_ensure_pdf_summaries_skips_items_without_content():
    items = [_item(content="", summary="")]

    with patch.object(summarizer, "summarize_article") as mock_summarize:
        updated = summarizer.ensure_pdf_summaries(items)

    mock_summarize.assert_not_called()
    assert updated is False


def test_ensure_pdf_summaries_does_not_persist_when_gemini_returns_empty():
    items = [_item(content="원문 있음", summary="")]

    with patch.object(summarizer, "summarize_article", return_value=""), \
         patch("db.update_mention_summary") as mock_update:
        updated = summarizer.ensure_pdf_summaries(items)

    mock_update.assert_not_called()
    assert updated is False
    assert items[0]["summary"] == ""


def test_presummarize_top_pdf_items_returns_zero_when_no_mentions():
    with patch("db.get_mentions", return_value=[]):
        assert summarizer.presummarize_top_pdf_items() == 0


def test_presummarize_top_pdf_items_counts_only_newly_summarized_items():
    mentions = [{"id": 1}, {"id": 2}]
    news_items = [
        _item(title="첫번째", content="원문1", summary="", mention_id=1),
        _item(title="두번째", content="원문2", summary="이미 있음", mention_id=2),
    ]

    with patch("db.get_mentions", return_value=mentions), \
         patch("news_feed.own_brand_names", return_value=set()), \
         patch("news_feed.build_news_items", return_value=news_items), \
         patch.object(summarizer, "summarize_article", return_value="새 요약") as mock_summarize, \
         patch("db.update_mention_summary") as mock_update:
        updated_count = summarizer.presummarize_top_pdf_items(limit=5)

    mock_summarize.assert_called_once_with("첫번째", "원문1")
    mock_update.assert_called_once_with(1, "새 요약")
    assert updated_count == 1
