"""v8 구조 검증: DLsite 실제 결과 카드와 후보 평가를 분리한다."""
from io import BytesIO

import pytest

from experiments.dlsite_detector.candidate_scoring import assess_title
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.dlsite_search_cards import (
    UnknownSearchLayout, parse_search_cards,
)
from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable
from experiments.dlsite_detector.reverse_lookup import lookup_title, search_catalog_html

BASE = "https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/Game/"
URL = "https://www.dlsite.com/maniax/work/=/product_id/"
TITLE = "Example Garden"
CARD = """
<div id="search_result_list">
 <ul class="n_worklist" id="search_result_img_box">
  <li class="search_result_img_box_inner">
   <dl class="work_img_main"><dd class="work_name"><div class="multiline_truncate">
    <a href="/maniax/work/=/product_id/RJ123456.html">Example Garden</a>
   </div></dd></dl>
   <ul class="work_operation_btn table-ul">
     <li><a class="btn_cart" href="/maniax/work/=/product_id/RJ123456.html">Cart</a></li>
     <li><a class="btn_favorite" href="/maniax/work/=/product_id/RJ123456.html">Like</a></li>
   </ul>
  </li>
 </ul>
</div>
"""
EXTRA = '<aside class="recommend"><a href="/maniax/work/=/product_id/RJ999999.html">Example Garden Deluxe</a></aside>'


class Response:
    def __init__(self, url, body):
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.body = BytesIO(body.encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.body.read(size)
    def geturl(self):
        return self.url


def product(code, title=TITLE):
    return Product(code, title, "", "maniax", URL + code + ".html")


def test_dlsite_scope_rejects_recommended_and_cart_links():
    rows = parse_search_cards(EXTRA + CARD + EXTRA, BASE)
    assert len(rows) == 1
    assert rows[0]["code"] == "RJ123456"
    assert rows[0]["title"] == TITLE
    assert rows[0]["scope"] == "search_result"


def test_dlsite_search_html_uses_scoped_cards_not_global_links():
    rows = search_catalog_html(
        "Example Garden", "maniax",
        opener=lambda req, timeout: Response(req.full_url, EXTRA + CARD))
    assert [x["code"] for x in rows] == ["RJ123456"]


def test_dlsite_empty_page_is_not_a_recommendation_hit():
    assert parse_search_cards("<html><div>0 results</div>" + EXTRA + "</html>", BASE) == []


def test_dlsite_layout_change_is_reported_instead_of_silent_zero():
    malformed = '<ul class="other"><li class="search_result_img_box_inner">' + (
        '<a href="/maniax/work/=/product_id/RJ123456.html">Example Garden</a></li></ul>')
    with pytest.raises(UnknownSearchLayout):
        parse_search_cards(malformed, BASE)
    with pytest.raises(PublicHtmlUnavailable):
        search_catalog_html(
            "Example Garden", "maniax",
            opener=lambda req, timeout: Response(req.full_url, malformed))


def test_wrong_series_never_matches_with_or_without_code_context():
    for actual in ("BUZAMA 20", "BUZAMA 20 RJ123456 DLsite",
                   "ブザマストリーマーズ -侮挫魔20-"):
        result = assess_title("BUZAMA 2", actual)
        assert result.score == 0 and result.series_conflict
    assert assess_title("BUZAMA 2", "BUZAMA 2 RJ123456 DLsite").score > 0
    assert assess_title("BUZAMA 3", "ブザマストリーマーズ -侮挫魔3-").score > 0


def test_weak_official_result_does_not_prevent_bing_then_ddgs():
    calls = []
    def catalog(name, category):
        calls.append("official:" + category)
        if category == "maniax":
            return [{"title": "Example Garden Redux",
                     "url": URL + "RJ111111.html", "scope": "search_result"}]
        return []
    def bing(name):
        calls.append("bing")
        return [{"title": "Example Garden RJ222222 DLsite",
                 "href": "https://third.example/entry"}]
    def ddgs(name):
        calls.append("ddgs")
        return [{"title": "Example Garden RJ333333",
                 "href": "https://third.example/another"}]
    products = {
        "RJ111111": product("RJ111111", "Example Garden Redux"),
        "RJ222222": product("RJ222222", "Example Garden"),
        "RJ333333": product("RJ333333", "Example Garden"),
    }
    result = lookup_title(
        "Example Garden", catalog_search=catalog, rss_search=bing, meta_search=ddgs,
        external_search=lambda *args: [], engine_search=lambda *args: [],
        fetcher=lambda code: products[code],
    )
    assert "bing" in calls and "ddgs" in calls
    assert calls.index("bing") < calls.index("ddgs")
    assert calls[0] == "official:maniax"
    assert set(m.code for m in result.matches) == set(products)
    assert result.status == "candidates"  # multiple possible works -> not confirmed
    assert any(x["code"] == "RJ111111" for x in result.catalog_review)
    assert all("reason" in x and "decision" in x for x in result.catalog_review)


def test_two_different_exact_official_codes_cannot_be_auto_confirmed():
    def catalog(name, category):
        if category == "maniax":
            return [{"title": TITLE, "url": URL + code + ".html",
                     "scope": "search_result"} for code in ("RJ123456","RJ654321")]
        return []
    result = lookup_title(
        TITLE, catalog_search=catalog, rss_search=lambda q: [], meta_search=lambda q: [],
        engine_search=lambda *args: [], external_search=lambda *args: [],
        fetcher=lambda code: product(code),
    )
    assert len(result.matches) == 2
    assert result.status == "candidates"


def test_unique_exact_official_code_still_skips_web_and_confirms():
    result = lookup_title(
        TITLE, catalog_search=lambda q, cat: [
            {"title": TITLE, "url": URL + "RJ123456.html",
             "scope": "search_result"}] if cat == "maniax" else [],
        rss_search=lambda q: (_ for _ in ()).throw(AssertionError("unnecessary Bing")),
        meta_search=lambda q: (_ for _ in ()).throw(AssertionError("unnecessary DDGS")),
        engine_search=lambda *args: [], external_search=lambda *args: [],
        fetcher=lambda code: product(code))
    assert result.status == "confirmed"
    assert result.matches[0].confidence == "exact_title"
