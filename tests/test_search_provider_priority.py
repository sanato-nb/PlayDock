"""검색 우선순위: DLsite 공식 검색 > Bing RSS > DDGS, 별칭 발견 시 공식 재검색."""
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable
from experiments.dlsite_detector.reverse_lookup import lookup_title


def product(code="RJ123456", title="Example Garden"):
    return Product(code, title, "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def never(*args):
    raise AssertionError("관련 후보가 있으면 후순위 검색엔진을 호출하면 안 됩니다.")


def official_hit(name, category):
    if category == "maniax":
        return [{"title": "Example Garden",
                 "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
    return []


def test_official_catalog_first_and_success_skips_rss_ddgs():
    result = lookup_title(
        "Example Garden.zip",
        catalog_search=official_hit, rss_search=never, meta_search=never,
        engine_search=never, external_search=never,
        fetcher=lambda code: product(code),
    )
    assert result.status == "confirmed"
    assert result.providers == (
        {"provider": "dlsite_maniax", "query": "Example Garden",
         "state": "ok", "count": 1},
    )


def test_bing_rss_second_when_official_search_returns_no_related_hit():
    rss = lambda name: [{"title": "Example Garden [RJ123456]",
                         "body": "DLsite product",
                         "href": "https://example.org/review"}]
    result = lookup_title(
        "Example Garden.zip", catalog_search=lambda *args: [],
        rss_search=rss, meta_search=never, engine_search=never,
        external_search=never, fetcher=lambda code: product(code),
    )
    assert result.status in ("confirmed", "candidates")
    assert result.matches[0].code == "RJ123456"
    providers = [p["provider"] for p in result.providers]
    assert providers[:4] == ["dlsite_" + c for c in ("maniax", "home", "soft", "girls")]
    assert providers[-1] == "bing_rss"


def test_ddgs_third_only_after_bing_rss_no_result():
    calls = []
    def rss(name):
        calls.append("bing")
        return []
    def meta(name):
        calls.append("ddgs")
        return [{"title": "Example Garden RJ123456",
                 "href": "https://example.org/info",
                 "body": "DLsite product"}]
    result = lookup_title(
        "Example Garden.zip", catalog_search=lambda *args: [],
        rss_search=rss, meta_search=meta, engine_search=never,
        external_search=never, fetcher=lambda code: product(code),
    )
    assert result.matches[0].code == "RJ123456"
    assert calls == ["bing", "ddgs"]
    providers = [p["provider"] for p in result.providers]
    assert providers.index("bing_rss") < providers.index("ddgs_meta")
    assert providers[0] == "dlsite_maniax"


def test_catalog_http_failure_still_falls_back_to_bing():
    def blocked(*args):
        raise PublicHtmlUnavailable("HTTP 403")
    result = lookup_title(
        "Example Garden.zip", catalog_search=blocked,
        rss_search=lambda name: [{"title": "Example Garden RJ123456",
                                  "href": "https://example.org/game"}],
        meta_search=never, engine_search=never, external_search=never,
        fetcher=lambda code: product(code),
    )
    assert result.matches[0].code == "RJ123456"
    assert result.providers[0]["state"] == "error"
    assert result.providers[0]["detail"] == "HTTP 403"
    assert result.providers[-1]["provider"] == "bing_rss"


def test_explicit_japanese_alias_after_bing_is_researched_on_official_catalog():
    visited = []
    def catalog(title, category):
        visited.append((title, category))
        if title == "魔法少女アリス" and category == "maniax":
            return [{"title": "魔法少女アリス",
                     "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
        return []
    result = lookup_title(
        "한국어 게임 제목.zip", catalog_search=catalog,
        rss_search=lambda name: [{"title": "한국어 게임 제목 소개",
                                  "body": "원제: 魔法少女アリス",
                                  "href": "https://example.org/wiki"}],
        meta_search=lambda name: [], engine_search=never,
        external_search=never,
        fetcher=lambda code: product(code, "魔法少女アリス"),
    )
    assert result.status == "candidates"
    assert result.matches[0].code == "RJ123456"
    assert ("魔法少女アリス", "maniax") in visited
    assert visited[0] == ("한국어 게임 제목", "maniax")
    assert all(visited.count(pair) == 1 for pair in set(visited))


def test_existing_filename_code_skips_all_discovery_engines():
    result = lookup_title(
        "Example Garden [RJ123456].zip",
        catalog_search=never, rss_search=never, meta_search=never,
        engine_search=never, external_search=never,
        fetcher=lambda code: product(code),
    )
    assert result.status == "confirmed"
    assert result.matches[0].code == "RJ123456"
    assert result.providers == ()
