import threading
import time
from datetime import datetime as real_datetime
from unittest.mock import patch

import pytest

import report_pdf


@pytest.fixture(autouse=True)
def _reset_pdf_cache():
    """각 테스트를 빈 캐시로 시작한다 — 단일 `_cache` 전역 슬롯 하나만 리셋하면 된다
    (예전에는 `_cache_key`/`_cache_bytes` 두 변수를 각 테스트마다 손으로 초기화했다)."""
    report_pdf._cache = None
    yield
    report_pdf._cache = None


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


def _item_with_id(mention_id, summary=""):
    item = _item("제목")
    item["mention_id"] = mention_id
    item["summary"] = summary
    # news_feed.build_news_items()가 실제로 하는 것과 동일하게, summary가 있으면
    # desc_long(카드 본문에 실제로 렌더링되는 필드)에 반영한다. mention_id/summary
    # 자체는 build_deck_html()이 읽지 않으므로, 이걸 안 하면 "summary가 바뀌었는데
    # 렌더링된 HTML은 그대로"인 상황이 되어 콘텐츠 해시 기반 캐시로는 변화가
    # 감지되지 않는다 — 이 헬퍼가 실제 데이터 흐름을 흉내 내야 테스트가 의미 있다.
    if summary:
        item["desc_long"] = [summary]
    return item


def test_get_or_generate_pdf_bytes_returns_cached_bytes_for_same_inputs():
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", return_value=b"pdf-bytes") as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

    assert first == b"pdf-bytes"
    assert second == b"pdf-bytes"
    mock_gen.assert_called_once_with(items, 10, 2)


def test_get_or_generate_pdf_bytes_regenerates_when_items_change():
    items_v1 = [_item_with_id(1, "")]
    items_v2 = [_item_with_id(1, "요약 생김")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        first = report_pdf.get_or_generate_pdf_bytes(items_v1, total_count=10, ai_count=2)
        second = report_pdf.get_or_generate_pdf_bytes(items_v2, total_count=10, ai_count=2)

    assert first == b"v1"
    assert second == b"v2"
    assert mock_gen.call_count == 2


def test_get_or_generate_pdf_bytes_regenerates_when_total_count_changes():
    items = [_item_with_id(1, "요약1")]

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)
        report_pdf.get_or_generate_pdf_bytes(items, total_count=11, ai_count=2)

    assert mock_gen.call_count == 2


def test_get_or_generate_pdf_bytes_regenerates_when_rendered_date_changes():
    """표지의 날짜 줄(datetime.now() 기준)은 손으로 고른 필드 목록에는 없었지만,
    콘텐츠 해시 키는 build_deck_html()이 실제로 만든 HTML을 해시하므로 날짜가
    바뀌면 자동으로 키도 바뀐다 — items/total_count/ai_count가 완전히 같아도
    "오늘 날짜"가 바뀌면 캐시가 어제 날짜를 박제해서 돌려주면 안 된다."""
    items = [_item_with_id(1, "요약1")]

    with patch("report_pdf.datetime") as mock_dt, \
         patch.object(report_pdf, "generate_pdf_bytes", side_effect=[b"v1", b"v2"]) as mock_gen:
        mock_dt.now.return_value = real_datetime(2026, 1, 1)
        first = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

        mock_dt.now.return_value = real_datetime(2026, 1, 2)
        second = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

    assert first == b"v1"
    assert second == b"v2"
    assert mock_gen.call_count == 2


def test_get_or_generate_pdf_bytes_single_flight_for_concurrent_cache_miss():
    """콜드 캐시에 같은 콘텐츠로 동시에 여러 스레드가 들어오면, Chromium 렌더링
    (generate_pdf_bytes)은 정확히 한 번만 일어나고 나머지는 그 결과를 공유해야
    한다 — 락이 없다면 N개 스레드가 각자 Chromium을 띄우거나(낭비), 서로 다른
    입력이 섞여 들어올 때 캐시가 (다른 스레드의 key, 이 스레드의 bytes) 같은
    잘못된 조합으로 오염될 수 있다(이 테스트는 전자를, 그 위의 오염 시나리오는
    _cache를 단일 튜플로 원자적으로 갈아치우는 구조 자체로 방지된다)."""
    items = [_item_with_id(1, "요약1")]
    call_count = 0
    count_lock = threading.Lock()

    def slow_generate(items, total_count, ai_count):
        nonlocal call_count
        with count_lock:
            call_count += 1
        time.sleep(0.05)
        return b"pdf-bytes"

    results = [None] * 8

    def worker(idx):
        results[idx] = report_pdf.get_or_generate_pdf_bytes(items, total_count=10, ai_count=2)

    with patch.object(report_pdf, "generate_pdf_bytes", side_effect=slow_generate):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert call_count == 1
    assert all(r == b"pdf-bytes" for r in results)
