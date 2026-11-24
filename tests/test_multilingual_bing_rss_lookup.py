"""한국어·영어·일본어 이름/원제 검색과 RSS 대체 경로 회귀 검사."""
from __future__ import annotations

from io import BytesIO

import pytest

from experiments.dlsite_detector.bing_rss import parse_bing_rss, search_bing_rss
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.multilingual_search import (
    title_candidates, explicit_original_titles,
)
from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable
from experiments.dlsite_detector.reverse_lookup import lookup_title

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Bing</title>
<item><title>Translated Garden [RJ123456]</title>
<link>https://example.org/info</link>
<description>DLsite game RJ123456</description></item>
<item><title>Other</title><link>http://example.org/unsafe</link></item>
</channel></rss>"""


class MockResponse:
    def __init__(self, url, data=RSS, content_type="application/rss+xml"):
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.body = BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body.read(size)

    def geturl(self):
        return self.url


def product(code="RJ123456", title="魔法少女アリス"):
    return Product(code, title, "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def forbidden(*args):
    raise AssertionError("이미 품번이 있는 경우 검색 엔진을 호출하지 않아야 함")


def test_bilingual_filename_has_separate_language_queries():
    q = title_candidates("번역 게임 제목 (Translated Garden) [v1.2] [한국어].7z")
    assert q == ("Translated Garden", "번역 게임 제목",
                 "번역 게임 제목 (Translated Garden)")


def test_japanese_filename_searches_original_not_machine_translation():
    q = title_candidates("魔法少女アリス [번역].zip")
    assert q == ("魔法少女アリス",)


def test_combined_games_are_searched_as_separate_titles():
    q = title_candidates("Adventure One + Adventure Two [v1.1].zip")
    assert q[:2] == ("Adventure One", "Adventure Two")


def test_title_candidates_not_include_local_paths_or_patch_notes():
    q = title_candidates(r"C:\private\key\번역 게임 제목 (Translated Garden) [노모] [v1.2].rar")
    assert q[0] == "Translated Garden"
    assert all("private" not in s and "key" not in s and "노모" not in s for s in q)


def test_original_alias_from_explicit_related_search_result_only():
    rows = [
        {"title": "번역 게임 제목 리뷰",
         "body": "작품 소개 - 원제: 魔法少女アリス"},
        {"title": "무관한 다른 게임",
         "body": "원제: 淫魔の大冒険"},
    ]
    assert explicit_original_titles(rows, ("번역 게임 제목",)) == ("魔法少女アリス",)


def test_unlabeled_japanese_words_do_not_become_alias():
    rows = [{"title": "번역 게임 제목", "body": "일본어 안내 日本語の作品名"}]
    assert explicit_original_titles(rows, ("번역 게임 제목",)) == ()


def test_bing_rss_extracts_structured_items():
    rows = parse_bing_rss(RSS)
    assert len(rows) == 1
    assert rows[0]["title"] == "Translated Garden [RJ123456]"
    assert rows[0]["body"] == "DLsite game RJ123456"


def test_bing_rss_rejects_html_and_doctype():
    with pytest.raises(PublicHtmlUnavailable):
        parse_bing_rss(b"<html><body>captcha</body></html>")
    with pytest.raises(PublicHtmlUnavailable):
        parse_bing_rss(b'<!DOCTYPE rss [<!ENTITY x "y">]><rss/>')


def test_bing_rss_url_is_encoded_without_api_key():
    seen = []
    def opener(req, timeout):
        url = req.full_url
        seen.append(url)
        return MockResponse(url)
    found = search_bing_rss("번역 게임 제목", opener=opener)
    assert len(found) == 1
    assert "format=rss" in seen[0]
    assert "q=" in seen[0] and "DLsite" in seen[0]
    assert "api_key" not in seen[0]


def test_code_from_rss_requires_official_fetch_and_stays_candidate_when_translated():
    rss = lambda q: [{
        "title": "번역 게임 제목 - 배포 정보",
        "body": "DLsite 작품 코드 RJ123456",
        "href": "https://example.org/wiki",
    }]
    result = lookup_title(
        "번역 게임 제목.zip", meta_search=lambda q: [],
        rss_search=rss, catalog_search=lambda *args: [],
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert result.status == "candidates"
    assert result.matches[0].source == "bing_rss"
    assert result.matches[0].code == "RJ123456"
    assert result.matches[0].title == "魔法少女アリス"
    assert any(p["provider"] == "bing_rss" for p in result.providers)


def test_discovered_japanese_original_is_searched_at_dlsite_without_claiming_confirmation():
    calls = []
    def catalog(name, category):
        calls.append((name, category))
        if name == "魔法少女アリス" and category == "maniax":
            return [{"title": "魔法少女アリス",
                     "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}]
        return []
    rss = lambda _: [{"title": "번역 게임 제목 안내",
                      "body": "일본어 원제: 魔法少女アリス",
                      "href": "https://example.org/game"}]
    result = lookup_title(
        "번역 게임 제목.zip", meta_search=lambda _: [], rss_search=rss,
        catalog_search=catalog,
        engine_search=forbidden, external_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert ("魔法少女アリス", "maniax") in calls
    assert result.status == "candidates"
    assert result.matches[0].code == "RJ123456"
    assert result.matches[0].confidence == "official_code"


def test_original_japanese_filename_exact_match_can_confirm():
    catalog = lambda name, category: ([{
        "title": "魔法少女アリス",
        "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
    }] if category == "maniax" else [])
    result = lookup_title(
        "魔法少女アリス.zip", meta_search=lambda _: [],
        rss_search=lambda _: [], catalog_search=catalog,
        engine_search=forbidden, external_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert result.status == "confirmed"


def test_translated_multi_alias_name_retries_official_catalog_separately():
    searched = []
    def catalog(name, category):
        searched.append(name)
        return []
    result = lookup_title(
        "번역 게임 제목 (Translated Garden).zip",
        meta_search=lambda _: [], rss_search=lambda _: [],
        catalog_search=catalog,
        engine_search=lambda *a: [],
        external_search=lambda *a: [],
    )
    assert result.status == "no_candidate"
    assert searched[0] == "Translated Garden"
    assert "번역 게임 제목" in searched


def test_embedded_rj_never_performs_language_or_rss_search():
    result = lookup_title(
        "번역 게임 제목 (Translated Garden) [RJ123456].zip",
        meta_search=forbidden, rss_search=forbidden,
        catalog_search=forbidden, external_search=forbidden,
        engine_search=forbidden, fetcher=lambda code: product(code),
    )
    assert result.status == "confirmed"
    assert result.matches[0].code == "RJ123456"
