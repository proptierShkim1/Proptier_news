from crawlers import article_content


class _FakeResponse:
    def __init__(self, html, status_ok=True, encoding="utf-8"):
        self.content = html.encode(encoding)
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise Exception("HTTP error")


def _mock_get(monkeypatch, html, status_ok=True, encoding="utf-8"):
    monkeypatch.setattr(
        article_content.requests, "get",
        lambda url, headers, timeout: _FakeResponse(html, status_ok, encoding),
    )


def test_fetch_content_extracts_text_from_known_selector(monkeypatch):
    html = """
    <html><body>
      <div id="dic_area">
        전세사기 피해를 예방하기 위한 새로운 서비스가 오늘 출시되었다.
        관련 업계에서는 이번 서비스가 시장에 미칠 영향에 주목하고 있다.
      </div>
    </body></html>
    """
    _mock_get(monkeypatch, html)

    result = article_content.fetch_content("https://example.com/news/1")

    assert "전세사기 피해를 예방하기 위한 새로운 서비스가 오늘 출시되었다." in result
    assert "관련 업계에서는 이번 서비스가 시장에 미칠 영향에 주목하고 있다." in result


def test_fetch_content_falls_back_to_article_tag_when_no_known_selector_matches(monkeypatch):
    html = """
    <html><body>
      <div class="totally-unknown-layout">
        <article>
          부동산 시장 전문가들은 이번 규제 완화가 거래량 회복에 도움이 될 것으로 내다봤다.
          다만 지역별 온도차는 여전할 것이라는 분석도 함께 나왔다.
        </article>
      </div>
    </body></html>
    """
    _mock_get(monkeypatch, html)

    result = article_content.fetch_content("https://example.com/news/2")

    assert "부동산 시장 전문가들은 이번 규제 완화가 거래량 회복에 도움이 될 것으로 내다봤다." in result


def test_fetch_content_strips_script_and_style_tags_inside_matched_container(monkeypatch):
    html = """
    <html><body>
      <div id="dic_area">
        <script>var ad = "should not appear";</script>
        <style>.ad { display:none; }</style>
        본문 내용만 추출되어야 하며 광고 스크립트나 스타일 코드는 섞이면 안 된다는 것을
        검증하기 위한 문단이다. 이 문단은 최소 길이 기준을 넘기기 위해 문장을 조금 더
        이어서 작성했다.
      </div>
    </body></html>
    """
    _mock_get(monkeypatch, html)

    result = article_content.fetch_content("https://example.com/news/3")

    assert "should not appear" not in result
    assert "display:none" not in result
    assert "본문 내용만 추출되어야 하며" in result


def test_fetch_content_returns_empty_string_when_no_container_has_enough_text(monkeypatch):
    html = """
    <html><body>
      <div class="totally-unknown-layout">짧음</div>
    </body></html>
    """
    _mock_get(monkeypatch, html)

    result = article_content.fetch_content("https://example.com/news/4")

    assert result == ""


def test_fetch_content_returns_empty_string_on_http_error(monkeypatch):
    _mock_get(monkeypatch, "<html></html>", status_ok=False)

    result = article_content.fetch_content("https://example.com/news/5")

    assert result == ""


def test_fetch_content_decodes_euc_kr_page_without_charset_header(monkeypatch):
    """서버가 HTTP 헤더에 charset을 안 주고 EUC-KR로 응답해도, <meta charset> 태그를
    보고 정확히 디코딩해야 한다 — requests.text에 의존하면 ISO-8859-1로 잘못 넘겨짚어
    한글이 모지바케로 깨지는 실제 버그(다음/조선일보 등 원문 스크래핑에서 발견됨)."""
    html = """
    <html><head><meta charset="euc-kr"></head><body>
      <div id="dic_area">
        구리시 로또 아파트 청약 경쟁률이 역대 최고 수준을 기록하며 시장의 관심이
        집중되고 있다는 분석이 나왔다. 전문가들은 이번 청약 열기가 인근 지역
        분양 시장 전반에도 영향을 미칠 것으로 내다봤으며, 실수요자들의 관심도
        당분간 이어질 것으로 전망했다.
      </div>
    </body></html>
    """
    _mock_get(monkeypatch, html, encoding="euc-kr")

    result = article_content.fetch_content("https://example.com/news/7")

    assert "구리시 로또 아파트 청약 경쟁률이 역대 최고 수준을 기록하며" in result


def test_fetch_content_returns_empty_string_on_request_exception(monkeypatch):
    def _raise(url, headers, timeout):
        raise Exception("connection reset")

    monkeypatch.setattr(article_content.requests, "get", _raise)

    result = article_content.fetch_content("https://example.com/news/6")

    assert result == ""
