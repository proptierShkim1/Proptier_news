import report_pdf


def _item(title, firm="직방", channel="네이버", categories=None):
    return {
        "title": title, "url": "https://x/1", "firm": firm, "date": "2026-08-05",
        "categories": ["AI"] if categories is None else categories,
        "signal": "🤖 AI", "desc": ["요약"], "decision": ["이유"],
        "meta": f"🕒 2026-08-05 09:00 · {channel}",
    }


def test_build_deck_html_has_one_page_per_item_plus_cover():
    items = [_item(f"제목{i}") for i in range(3)]

    html = report_pdf.build_deck_html(items)

    assert html.count('<div class="page') == 1 + len(items)


def test_card_shows_brand_channel_and_categories_in_metagrid():
    items = [_item("제목", firm="직방", channel="구글", categories=["AI", "매물"])]

    html = report_pdf.build_deck_html(items)

    assert 'class="metagrid"' in html
    assert "직방" in html
    assert "구글" in html
    assert "AI, 매물" in html


def test_card_falls_back_to_dash_when_categories_empty():
    items = [_item("제목", categories=[])]

    html = report_pdf.build_deck_html(items)

    assert "일반" in html


def test_card_shows_shortcut_link_to_article_url():
    items = [_item("제목")]
    items[0]["url"] = "https://example.com/article/123"

    html = report_pdf.build_deck_html(items)

    assert 'class="metalink"' in html
    assert 'href="https://example.com/article/123"' in html
    assert "바로가기" in html


from unittest.mock import patch


def _item_with_id(mention_id, summary=""):
    item = _item("제목")
    item["mention_id"] = mention_id
    item["summary"] = summary
    return item


def test_get_or_generate_pdf_bytes_returns_cached_bytes_for_same_inputs():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", return_value=b"pdf-bytes") as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

    assert first == b"pdf-bytes"
    assert second == b"pdf-bytes"
    mock_gen.assert_called_once_with(items, 10, 2)


def test_get_or_generate_pdf_bytes_regenerates_when_items_change():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items_v1 = [_item_with_id(1, "")]
    items_v2 = [_item_with_id(1, "요약 생김")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items_v1, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items_v2, total_count=10, ai_count=2)

    assert first == b"v1"
    assert second == b"v2"
    assert mock_gen.call_count == 2


def test_get_or_generate_pdf_bytes_regenerates_when_total_count_changes():
    report_pdf._cache_key = None
    report_pdf._cache_bytes = None
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        report_pdf.get_or_generate_pdf_bytes(items, total_count=11, ai_count=2)

    assert mock_gen.call_count == 2
