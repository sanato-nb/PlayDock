"""API 키 없는 자동 다중 검색: 웹 결과 수집·품번 근거·회귀 테스트."""
from __future__ import annotations

import pytest

from experiments.dlsite_detector.metasearch_no_key import (
    BACKENDS, search_meta_no_key,
)
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.reverse_lookup import lookup_title
from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable


def official(code="RJ123456", title="日本語の作品名"):
    return Product(code, title, "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def forbidden(*_):
    raise AssertionError("이미 공식 품번을 얻었으므로 추가 이름 검색 금지")


def test_meta_search_extracts_title_url_and_summary():
    rows = search_meta_no_key(
        "한글 작품명",
        searcher=lambda q: [
            {"title": "한글 작품명", "href": "https://example.org/p/123",
             "body": "DLsite RJ123456 작품 소개"},
            {"title": "irrelevant", "href": "javascript:alert(1)", "body": "skip"},
        ],
    )
    assert len(rows) == 1
    assert rows[0]["body"] == "DLsite RJ123456 작품 소개"


def test_web_metas_can_confirm_official_code_but_not_translated_name():
    inputs = []
    def meta(title):
        inputs.append(title)
        return [{"title": "한글 작품명", "href": "https://community.example.net/post",
                 "body": "DLsite 품번 RJ123456 제작 게임"}]
    result = lookup_title(
        "한글 작품명 [v1.2].zip",
        meta_search=meta, catalog_search=forbidden,
        engine_search=forbidden, external_search=forbidden,
        fetcher=lambda code: official(code),
    )
    assert inputs == ["한글 작품명"]
    assert result.status == "candidates"
    assert result.matches[0].code == "RJ123456"
    assert result.matches[0].title == "日本語の作品名"
    assert result.matches[0].source == "ddgs_meta"
    assert result.matches[0].confidence == "official_code"
    assert result.providers[0]["provider"] == "ddgs_meta"


def test_meta_unverified_code_stays_candidate_and_no_fabricated_url():
    result = lookup_title(
        "한글 작품명.zip", meta_search=lambda _: [
            {"title": "한글 작품명 [RJ123456]",
             "href": "https://example.org/forum"}],
        catalog_search=forbidden, engine_search=forbidden,
        external_search=forbidden, fetcher=lambda code: None,
    )
    assert result.status == "candidates"
    assert result.matches[0].confidence == "search_candidate"
    assert result.matches[0].url == ""


def test_unrelated_meta_code_is_ignored_and_official_search_proceeds():
    calls = []
    def catalog(title, category):
        calls.append(category)
        return []
    result = lookup_title(
        "한글 작품명.zip",
        meta_search=lambda _: [
            {"title": "완전히 다른 작품 [RJ123456]",
             "href": "https://example.org/post"}],
        catalog_search=catalog,
        engine_search=lambda *args: [],
        external_search=lambda *args: [],
        fetcher=lambda code: official(code),
    )
    assert result.status == "no_candidate" and not result.matches
    assert calls == ["maniax", "home", "soft", "girls"]


def test_known_code_avoids_all_web_search_still():
    result = lookup_title("한글 작품명 [RJ123456].zip",
                          meta_search=forbidden,
                          catalog_search=forbidden, external_search=forbidden,
                          engine_search=forbidden,
                          fetcher=lambda code: official(code))
    assert result.status == "confirmed"
    assert result.matches[0].confidence == "filename_code_verified"


def test_auto_meta_falls_back_on_failure_not_falsely_declared_missing():
    def fail(_):
        raise PublicHtmlUnavailable("모든 메타 검색 엔진이 차단됨")
    result = lookup_title(
        "한글 작품명.zip", meta_search=fail,
        catalog_search=lambda *args: [],
        engine_search=lambda *args: [],
        external_search=lambda *args: [],
    )
    assert result.status == "no_candidate"
    assert any(p["provider"] == "ddgs_meta" and p["state"] == "error"
               for p in result.providers)


def test_meta_search_rejects_unsafe_and_duplicate_urls():
    rows = search_meta_no_key("한글 작품명", searcher=lambda _: [
        {"title": "ABC", "href": "http://example.org/insecure"},
        {"title": "ABC", "href": "https://example.org/valid"},
        {"title": "ABC again", "href": "https://example.org/valid"},
        {"title": "ABC", "href": "https://user:pass@example.org/credential"},
        {"title": "ABC", "href": "https://example.org/another"},
    ])
    assert len(rows) == 2
    assert all(r["href"].startswith("https://") for r in rows)


def test_meta_invalid_inputs_skip_search():
    assert search_meta_no_key("x", searcher=forbidden) == []
    assert search_meta_no_key("../", searcher=lambda _: []) == []


def test_ddgs_never_uses_google_automated_backend():
    assert "google" not in BACKENDS
    assert "duckduckgo" in BACKENDS
