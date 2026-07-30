from datetime import date

from crawlers import lh

_PAGE1_HTML = """
<div class="blog_box">
	<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077">
		<div class="desc">
			<strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
			<span class="date">2026-07-24</span>
		</div>
	</a>
</div>
<div class="board_list">
	<ul class="gallery_list type1">
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12072">
				<span class="desc">
					<strong class="title">신축매입임대 자금조달 부담 완화 등 전면 시행</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-07-20</span>
				</span>
			</a>
		</li>
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12069">
				<span class="desc">
					<strong class="title">한국토지주택공사(LH), 광명시흥 공공주택지구 보상 착수</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-07-14</span>
				</span>
			</a>
		</li>
	</ul>
</div>
"""

_PAGE2_HTML = """
<div class="blog_box">
	<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077">
		<div class="desc">
			<strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
			<span class="date">2026-07-24</span>
		</div>
	</a>
</div>
<div class="board_list">
	<ul class="gallery_list type1">
		<li>
			<a href="/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=11999">
				<span class="desc">
					<strong class="title">오래된 보도자료</strong>
					<span class="date"><strong class="label">등록일</strong> 2026-06-01</span>
				</span>
			</a>
		</li>
	</ul>
</div>
"""


def test_fetch_press_releases_parses_title_url_date_and_skips_featured_duplicate(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured.setdefault("pages", []).append(params["nPage"])
        captured["url"] = url

        class FakeResponse:
            text = _PAGE1_HTML if params["nPage"] == 1 else "<div></div>"

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert captured["url"] == "https://www.lh.or.kr/gallery.es"
    assert captured["pages"][0] == 1
    assert len(results) == 3
    first = results[0]
    assert first["title"] == "한국토지주택공사(LH), 2026년 기업설명회(IR) 개최"
    assert first["url"] == (
        "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077"
    )
    assert first["department"] == ""
    assert first["announced_at"] == "2026-07-24"
    assert first["view_count"] == 0


def test_fetch_press_releases_stops_paging_once_older_than_start_without_featured_tripping_it(monkeypatch):
    pages = [_PAGE1_HTML, _PAGE2_HTML]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["nPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    assert len(results) == 3
    assert all(r["announced_at"] >= "2026-07-01" for r in results)


def test_fetch_press_releases_normalizes_featured_item_url_across_pages(monkeypatch):
    """실사이트에서 featured 항목의 href는 nPage/vlist_no_npage 등 '현재 조회 중인 페이지'를
    반영해 페이지마다 querystring이 달라진다 (프로덕션 DB에서 중복 저장으로 확인된 버그) —
    list_no만으로 URL을 재구성해 페이지에 관계없이 항상 같은 URL이 나와야 한다."""
    page1 = """
    <div class="blog_box">
        <a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12077&nPage=1&vlist_no_npage=0&keyField=&orderby=">
            <div class="desc">
                <strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
                <span class="date">2026-07-24</span>
            </div>
        </a>
    </div>
    <div class="board_list"><ul class="gallery_list type1">
        <li><a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12072&nPage=1&vlist_no_npage=1&keyField=&orderby=">
            <span class="desc"><strong class="title">신축매입임대 자금조달 부담 완화</strong>
            <span class="date"><strong class="label">등록일</strong> 2026-07-20</span></span>
        </a></li>
    </ul></div>
    """
    page2 = """
    <div class="blog_box">
        <a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=12077&nPage=2&vlist_no_npage=0&keyField=&orderby=">
            <div class="desc">
                <strong class="title">한국토지주택공사(LH), 2026년 기업설명회(IR) 개최</strong>
                <span class="date">2026-07-24</span>
            </div>
        </a>
    </div>
    <div class="board_list"><ul class="gallery_list type1">
        <li><a href="/gallery.es?mid=a10502000000&bid=0003&b_list=8&act=view&list_no=11999&nPage=2&vlist_no_npage=1&keyField=&orderby=">
            <span class="desc"><strong class="title">오래된 보도자료</strong>
            <span class="date"><strong class="label">등록일</strong> 2026-06-01</span></span>
        </a></li>
    </ul></div>
    """
    pages = [page1, page2]

    def fake_get(url, params, headers, timeout):
        class FakeResponse:
            text = pages[params["nPage"] - 1]

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(lh.requests, "get", fake_get)

    results = lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27))

    featured_urls = [r["url"] for r in results if r["title"].endswith("기업설명회(IR) 개최")]
    assert featured_urls == [
        "https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12077"
    ]


def test_fetch_press_releases_returns_empty_list_on_request_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise lh.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(lh.requests, "get", fake_get)

    assert lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []


def test_fetch_press_releases_returns_empty_list_when_board_missing(monkeypatch):
    class FakeResponse:
        text = "<div>구조가 다름</div>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(lh.requests, "get", lambda url, params, headers, timeout: FakeResponse())

    assert lh.fetch_press_releases(date(2026, 7, 1), date(2026, 7, 27)) == []
