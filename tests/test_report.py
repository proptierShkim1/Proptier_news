from unittest.mock import patch

from views import report


def _item(title="제목", content="", summary="", mention_id=1):
    return {
        "title": title, "content": content, "summary": summary, "mention_id": mention_id,
        "desc": ["짧은 요약"], "desc_long": ["긴 발췌"],
    }


def test_ensure_pdf_summaries_calls_gemini_only_for_items_with_content_and_no_summary():
    items = [_item(content="원문 있음", summary="")]

    with patch.object(report.summarizer, "summarize_article", return_value="새 AI 요약") as mock_summarize, \
         patch.object(report.db, "update_mention_summary") as mock_update:
        report._ensure_pdf_summaries(items)

    mock_summarize.assert_called_once_with("제목", "원문 있음")
    mock_update.assert_called_once_with(1, "새 AI 요약")
    assert items[0]["summary"] == "새 AI 요약"
    assert items[0]["desc_long"] == ["새 AI 요약"]


def test_ensure_pdf_summaries_skips_items_that_already_have_a_summary():
    items = [_item(content="원문 있음", summary="이미 있는 요약")]

    with patch.object(report.summarizer, "summarize_article") as mock_summarize:
        report._ensure_pdf_summaries(items)

    mock_summarize.assert_not_called()
    assert items[0]["desc_long"] == ["긴 발췌"]


def test_ensure_pdf_summaries_skips_items_without_content():
    items = [_item(content="", summary="")]

    with patch.object(report.summarizer, "summarize_article") as mock_summarize:
        report._ensure_pdf_summaries(items)

    mock_summarize.assert_not_called()


def test_ensure_pdf_summaries_does_not_persist_when_gemini_returns_empty():
    items = [_item(content="원문 있음", summary="")]

    with patch.object(report.summarizer, "summarize_article", return_value=""), \
         patch.object(report.db, "update_mention_summary") as mock_update:
        report._ensure_pdf_summaries(items)

    mock_update.assert_not_called()
    assert items[0]["summary"] == ""
