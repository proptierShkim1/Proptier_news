import report_pdf


def _item(title, rank=1):
    return {
        "title": title, "url": "https://x/1", "firm": "직방", "date": "2026-08-05",
        "categories": ["AI"], "signal": "🤖 AI", "desc": ["요약"], "decision": ["이유"],
        "meta": "🕒 2026-08-05 09:00 · 네이버",
    }


def test_summary_page_count_is_zero_for_no_items():
    assert report_pdf.summary_page_count(0) == 0


def test_summary_page_count_rounds_up_to_a_full_page():
    assert report_pdf.summary_page_count(report_pdf.SUMMARY_PAGE_SIZE + 1) == 2


def test_summary_page_count_exact_multiple_of_page_size():
    assert report_pdf.summary_page_count(report_pdf.SUMMARY_PAGE_SIZE * 3) == 3


def test_build_deck_html_without_summary_items_has_only_cover_and_detail_pages():
    items = [_item(f"제목{i}") for i in range(3)]

    html = report_pdf.build_deck_html(items)

    assert html.count('<div class="page') == 1 + len(items)
    assert 'class="repsummary"' not in html


def test_build_deck_html_appends_summary_pages_covering_the_rest():
    items = [_item(f"제목{i}") for i in range(3)]
    summary_items = [_item(f"요약{i}") for i in range(report_pdf.SUMMARY_PAGE_SIZE + 2)]

    html = report_pdf.build_deck_html(items, summary_items=summary_items)

    expected_summary_pages = report_pdf.summary_page_count(len(summary_items))
    assert html.count('<div class="page') == 1 + len(items) + expected_summary_pages
    assert html.count('class="repsummary"') == expected_summary_pages
    assert "요약0" in html and f"요약{len(summary_items) - 1}" in html
