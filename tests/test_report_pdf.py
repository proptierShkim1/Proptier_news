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
