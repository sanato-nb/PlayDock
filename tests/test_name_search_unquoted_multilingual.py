"""압축파일에 품번이 없는 경우: 번역명 검색과 웹 품번 근거 회귀 테스트."""
from __future__ import annotations

from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.reverse_lookup import (
    lookup_title, parse_web_code_hints, search_engine_html,
)
from experiments.dlsite_detector.search_terms import title_web_queries


class Response:
    def __init__(self, url, html):
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.body = BytesIO(html.encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self, count):
        return self.body.read(count)

    def geturl(self):
        return self.url


def product(code, title="日本語の正式な作品名"):
    return Product(code, title, "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def no_search(*_):
    raise AssertionError("명시 품번이 있으면 제목 검색을 호출하지 않는다")


def test_aliases_use_english_name_without_deleting_original():
    queries = title_web_queries("우주의 보물 (Universe Treasure) [v1.21] [한국어].7z")
    assert queries == ("Universe Treasure", "우주의 보물 (Universe Treasure)")


def test_plain_korean_title_remains_unmodified():
    assert title_web_queries("황성의 빅토리아스 [v1.0.1].7z") == ("황성의 빅토리아스",)


def test_filename_path_does_not_leak_into_web_queries():
    queries = title_web_queries("C:\\private\\token\\우주의 보물 (Universe Treasure).zip")
    assert len(queries) == 2
    assert all("private" not in q and "token" not in q for q in queries)


def test_html_search_is_broad_and_unquoted_not_site_limited():
    seen = []
    def opener(request, timeout):
        seen.append(request.full_url)
        return Response(request.full_url, "<html></html>")
    assert search_engine_html("우주의 보물", "google_html", opener=opener) == []
    query = parse_qs(urlsplit(seen[0]).query)["q"][0]
    assert query == "우주의 보물 DLsite RJ"
    assert 'site:' not in query and '"' not in query


def test_web_result_links_korean_title_to_rj_even_when_official_title_japanese():
    calls = []
    def engine(title, provider):
        calls.append((title, provider))
        if title == "우주의 보물" and provider == "bing_html":
            return [{"title": "우주의 보물 (다운로드) [RJ123456]",
                     "url": "https://community.example.org/game-info/123"}]
        return []
    found = lookup_title(
        "우주의 보물 [v1.0].zip",
        catalog_search=lambda *args: [], engine_search=engine,
        external_search=lambda *args: [],
        fetcher=lambda code: product(code),
    )
    assert found.status == "candidates"  # 번역명과 일본어 정식 제목 직접 일치 미검증
    assert found.matches[0].code == "RJ123456"
    assert found.matches[0].title == "日本語の正式な作品名"
    assert found.matches[0].source == "bing_html"
    assert "확인" in found.matches[0].note
    assert calls == [("우주의 보물", "bing_html")]


def test_candidate_from_other_website_without_official_page_stays_unverified():
    found = lookup_title(
        "우주의 보물.zip", catalog_search=lambda *args: [],
        engine_search=lambda *_: [{"title": "우주의 보물 [RJ123456]",
                                   "url": "https://example.org/game"}],
        fetcher=lambda *_: None,
    )
    assert found.status == "candidates"
    assert found.matches[0].confidence == "search_candidate"
    assert found.matches[0].url == ""


def test_irrelevant_rj_in_link_text_is_rejected():
    result = parse_web_code_hints(
        '<a href="https://example.org/post">다른 게임 [RJ123456]</a>',
        "https://www.bing.com/search?q=test", "우주의 보물",
    )
    assert not result


def test_web_code_hint_is_extractable_from_search_anchor():
    html = ('<div class="b_algo"><a href="https://example.org/game">'
            '우주의 보물 [RJ123456]</a></div>')
    def opener(request, timeout):
        return Response(request.full_url, html)
    rows = search_engine_html("우주의 보물", "bing_html", opener=opener)
    assert len(rows) == 1
    assert rows[0]["title"] == "우주의 보물 [RJ123456]"


def test_catalog_irrelevant_links_dont_suppress_web_search():
    irrelevant = [{"title": "무관한 작품", "url":
                   "https://www.dlsite.com/maniax/work/=/product_id/RJ999999.html"}]
    found = lookup_title(
        "우주의 보물",
        catalog_search=lambda *args: irrelevant,
        engine_search=lambda title, provider: (
            [{"title": "우주의 보물 [RJ123456]",
              "url": "https://example.net/post"}]
            if provider == "bing_html" else []),
        external_search=lambda *args: [],
        fetcher=lambda code: product(code),
    )
    assert [match.code for match in found.matches] == ["RJ123456"]


def test_code_present_uses_only_official_fetcher():
    found = lookup_title(
        "우주의 보물 [RJ123456].zip",
        catalog_search=no_search, engine_search=no_search,
        external_search=no_search, fetcher=lambda code: product(code),
    )
    assert found.status == "confirmed" and len(found.matches) == 1
    assert found.matches[0].confidence == "filename_code_verified"
