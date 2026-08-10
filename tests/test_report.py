from unittest.mock import patch

from views import report


def _item(title="제목", content="", summary="", mention_id=1):
    return {
        "title": title, "content": content, "summary": summary, "mention_id": mention_id,
        "desc": ["짧은 요약"], "desc_long": ["긴 발췌"],
    }


def test_ensure_pdf_summaries_delegates_to_shared_summarizer_helper():
    items = [_item(content="원문 있음", summary="")]

    with patch.object(report.summarizer, "ensure_pdf_summaries", return_value=True) as mock_ensure, \
         patch.object(report.cached_db.get_mentions, "clear") as mock_clear:
        report._ensure_pdf_summaries(items)

    mock_ensure.assert_called_once_with(items)
    mock_clear.assert_called_once()


def test_ensure_pdf_summaries_skips_cache_clear_when_nothing_updated():
    items = [_item(content="원문 있음", summary="이미 있는 요약")]

    with patch.object(report.summarizer, "ensure_pdf_summaries", return_value=False), \
         patch.object(report.cached_db.get_mentions, "clear") as mock_clear:
        report._ensure_pdf_summaries(items)

    mock_clear.assert_not_called()


def test_report_view_wires_pdf_button_to_cache_aware_generator():
    from report_pdf import get_or_generate_pdf_bytes

    assert report.get_or_generate_pdf_bytes is get_or_generate_pdf_bytes
    assert not hasattr(report, "generate_pdf_bytes")
