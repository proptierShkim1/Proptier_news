from unittest.mock import patch

from views import report


def _item(title="제목", content="", summary="", mention_id=1, has_real_content=True):
    return {
        "title": title, "content": content, "summary": summary, "mention_id": mention_id,
        "desc": ["짧은 요약"], "desc_long": ["긴 발췌"], "has_real_content": has_real_content,
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


def test_select_pdf_items_excludes_items_without_real_content():
    items = [
        _item(title="본문 있음", mention_id=1, has_real_content=True),
        _item(title="구글 채널 원문 못 얻음", mention_id=2, has_real_content=False),
        _item(title="본문 있음2", mention_id=3, has_real_content=True),
    ]

    selected = report._select_pdf_items(items)

    assert [it["mention_id"] for it in selected] == [1, 3]


def test_select_pdf_items_returns_up_to_limit_real_content_items():
    items = [_item(title=f"제목{i}", mention_id=i, has_real_content=True) for i in range(7)]

    selected = report._select_pdf_items(items, limit=5)

    assert len(selected) == 5


def test_report_view_wires_pdf_button_to_cache_aware_generator():
    from report_pdf import get_or_generate_pdf_bytes

    assert report.get_or_generate_pdf_bytes is get_or_generate_pdf_bytes
    assert not hasattr(report, "generate_pdf_bytes")
