"""이름↔품번 양방향 HTML 검색기: 인터넷 없이 검증 가능한 회귀 테스트."""
from __future__ import annotations

from io import BytesIO

from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.reverse_lookup import (
    lookup_code, lookup_title, parse_catalog_links, search_catalog_html, search_engine_html,
)


class Response:
    def __init__(self, url, html):
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.stream = BytesIO(html.encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.stream.read(n)

    def geturl(self):
        return self.url


def product(code="RJ123456", title="My Game", category="maniax"):
    return Product(code, title, "", category,
                   f"https://www.dlsite.com/{category}/work/=/product_id/{code}.html")


def test_search_catalog_extracts_official_links_without_api_calls():
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(request.full_url,
                        '<a href="/maniax/work/=/product_id/RJ123456.html">'
                        '<img alt="My Game"></a>'
                        '<a href="/maniax/help/">Help</a>')
    rows = search_catalog_html("My Game", "maniax", opener=opener)
    assert [row["code"] for row in rows] == ["RJ123456"]
    assert rows[0]["title"] == "My Game"
    assert "/fsr/" in calls[0] and "/api/" not in calls[0]


def test_search_catalog_escapes_path_injection():
    seen = []
    def opener(request, timeout):
        seen.append(request.full_url)
        return Response(request.full_url, "<html>No matches</html>")
    assert search_catalog_html("Title /?code=1", "home", opener=opener) == []
    assert "/keyword/Title%20%2F%3Fcode%3D1/" in seen[0]
    assert "/api/" not in seen[0]


def test_catalog_rejects_third_party_code_spoof_and_deduplicates():
    html = (
        '<a href="https://dlsite.com.evil.org/maniax/work/=/product_id/RJ999999.html">Bad</a>'
        '<a href="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html">My Game</a>'
        '<a href="/maniax/work/=/product_id/RJ123456.html">Duplicate</a>'
    )
    results = parse_catalog_links(html, "https://www.dlsite.com/maniax/fsr/=/")
    assert len(results) == 1 and results[0]["title"] == "My Game"


def test_code_lookup_returns_official_name_without_json_api():
    result = lookup_code("rj123456", fetcher=lambda code: product(code))
    assert result.status == "confirmed"
    assert result.matches[0].title == "My Game"
    assert result.matches[0].confidence == "official_code"
    assert result.to_dict()["direction"] == "code_to_title"


def test_code_lookup_rejects_wrong_format():
    for code in ("", "RJ123", "RJ123456/evil", "ST123456", "RJ123456;RJ888888"):
        assert lookup_code(code).status == "invalid"


def test_code_lookup_rejects_wrong_code_from_responder():
    result = lookup_code("RJ123456", fetcher=lambda _: product("RJ999999"))
    assert result.status == "unavailable"
    assert not result.matches


def test_code_lookup_missing_html_is_not_declared_nonexistent():
    result = lookup_code("RJ123456", fetcher=lambda _: None)
    assert result.status == "unavailable"
    assert "미등록 판정이 아닙니다" in result.warnings[0]


def test_title_lookup_verifies_exact_name_by_official_html():
    def search(title, category):
        return ([{"title": "My Game",
                  "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
                if category == "maniax" else [])
    result = lookup_title(
        "My Game [v1.2].zip",
        catalog_search=search,
        external_search=lambda *args: (_ for _ in ()).throw(AssertionError("no fallback")),
        fetcher=lambda code: product(code),
    )
    assert result.query == "My Game"
    assert result.status == "confirmed"
    assert result.matches[0].code == "RJ123456"
    assert result.matches[0].confidence == "exact_title"
    assert all("/api/" not in p.get("provider", "") for p in result.providers)


def test_title_lookup_keeps_unmatched_name_as_candidate():
    def search(title, category):
        return ([{"title": "My Game",
                  "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
                if category == "maniax" else [])
    result = lookup_title("Different Work", catalog_search=search,
                          engine_search=lambda *args: [], external_search=lambda *args: [],
                          fetcher=lambda code: product(code))
    assert result.status == "no_candidate"
    assert result.matches == ()
    assert any("품번 후보를 찾지 못했습니다" in w for w in result.warnings)


def test_title_lookup_keeps_search_candidate_when_product_html_blocked():
    def search(title, category):
        return ([{"title": "My Game",
                  "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
                if category == "maniax" else [])
    result = lookup_title("My Game", catalog_search=search,
                          fetcher=lambda _: None)
    assert result.status == "candidates"
    assert result.matches[0].confidence == "search_candidate"


def test_title_lookup_falls_back_to_general_public_html_when_dlsite_empty():
    searches = []
    def external(query, provider):
        searches.append((query, provider))
        return [{"title": "My Game", "href":
                 "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
    result = lookup_title("My Game", catalog_search=lambda *args: [],
                          engine_search=lambda *args: [], external_search=external,
                          fetcher=lambda code: product(code))
    assert searches == [('My Game DLsite RJ', "ddg_html")]
    assert result.status == "confirmed"


def test_title_lookup_unavailable_when_all_sites_fail():
    def broken(*args):
        raise RuntimeError("blocked")
    result = lookup_title("My Game", catalog_search=broken, external_search=broken,
                          engine_search=broken)
    assert result.status == "unavailable"
    assert len(result.providers) == 8
    assert all(p["state"] == "error" for p in result.providers)


def test_title_lookup_never_uses_arbitrary_website_codes():
    def external(query, provider):
        return [{"title": "My Game", "href": "https://evil.com/work/=/product_id/RJ123456.html"}]
    result = lookup_title("My Game", catalog_search=lambda *args: [],
                          engine_search=lambda *args: [], external_search=external)
    assert result.status == "no_candidate"
    assert not result.matches


def test_title_lookup_does_not_send_original_private_path():
    seen = []
    def catalog(title, category):
        seen.append(title)
        return []
    lookup_title("C:\\private\\My Game [v2.0].zip", catalog_search=catalog,
                 engine_search=lambda *args: [], external_search=lambda *args: [])
    assert seen and set(seen) == {"My Game"}


def test_title_lookup_short_query_rejected_without_network():
    assert lookup_title("A").status == "invalid"
    assert lookup_title("").status == "invalid"


def test_bing_html_extracts_only_valid_official_product_link():
    urls = []
    def opener(request, timeout):
        urls.append(request.full_url)
        return Response(request.full_url, (
            '<li class="b_algo"><h2><a '
            'href="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html">'
            'My Game</a></h2></li>'
            '<a href="https://evil.example.net/maniax/work/=/product_id/RJ999999.html">Fake</a>'
        ))
    matches = search_engine_html("My Game", "bing_html", opener=opener)
    assert [m["code"] for m in matches] == ["RJ123456"]
    assert "bing.com/search" in urls[0]
    assert "site%3A" not in urls[0] and "%22" not in urls[0]
    assert "DLsite+RJ" in urls[0]
    assert "/api/" not in urls[0]


def test_google_html_redirect_unwrapped_only_when_dlsite_product():
    def opener(request, timeout):
        return Response(request.full_url, (
            '<a href="/url?q=https%3A%2F%2Fwww.dlsite.com%2Fmaniax%2Fwork%2F%3D%2F'
            'product_id%2FRJ123456.html&amp;sa=U">My Game</a>'
            '<a href="/url?q=https%3A%2F%2Fevil.example.com%2Fanything">Bad</a>'
        ))
    matches = search_engine_html("My Game", "google_html", opener=opener)
    assert [m["code"] for m in matches] == ["RJ123456"]


def test_title_lookup_prefers_bing_html_to_blocked_ddg_when_official_empty():
    calls = []
    def engines(title, provider):
        calls.append(provider)
        return ([{"title": "My Game", "url":
                  "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
                if provider == "bing_html" else [])
    result = lookup_title("My Game", catalog_search=lambda *args: [],
                          engine_search=engines,
                          external_search=lambda *args: (_ for _ in ()).throw(AssertionError("not needed")),
                          fetcher=lambda code: product(code))
    assert result.status == "confirmed"
    assert calls == ["bing_html"]
