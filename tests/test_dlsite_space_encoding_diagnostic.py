"""DLsite URL의 공백은 경로에서 +로 표현해야 하는 회귀 검증.

Windows 실접속 A/B에서:
  keyword/Stardew%20Valley/ -> HTTP 403
  keyword/Stardew+Valley/  -> HTTP 200
"""
from io import BytesIO
from urllib.error import HTTPError

import pytest

from experiments.dlsite_detector.no_api_html import PublicHtmlUnavailable
from experiments.dlsite_detector.reverse_lookup import lookup_title, search_catalog_html


class Response:
    def __init__(self, url, html="<html></html>"):
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.body = BytesIO(html.encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount):
        return self.body.read(amount)

    def geturl(self):
        return self.url


def test_dlsite_search_space_is_plus_not_percent20():
    requested = []
    def opener(req, timeout):
        requested.append(req.full_url)
        return Response(req.full_url)
    assert search_catalog_html("Stardew Valley", "maniax", opener=opener) == []
    assert "/keyword/Stardew+Valley/" in requested[0]
    assert "%20" not in requested[0]


def test_search_path_escapes_literal_plus_to_percent2b():
    requested = []
    def opener(req, timeout):
        requested.append(req.full_url)
        return Response(req.full_url)
    assert search_catalog_html("A+B Game", "home", opener=opener) == []
    assert "/keyword/A%2BB+Game/" in requested[0]


def test_korean_search_separates_words_with_plus_and_preserves_encoding():
    requested = []
    def opener(req, timeout):
        requested.append(req.full_url)
        return Response(req.full_url)
    assert search_catalog_html("마왕의 비보", "maniax", opener=opener) == []
    assert "%20" not in requested[0]
    assert "+" in requested[0]
    assert "%EB" in requested[0]


def test_http_403_not_hidden_by_exception_type():
    def opener(req, timeout):
        raise HTTPError(req.full_url, 403, "Forbidden", {}, None)
    with pytest.raises(PublicHtmlUnavailable, match=r"HTTP 403"):
        search_catalog_html("Stardew Valley", "maniax", opener=opener)


def test_http_404_not_misidentified_as_normal_empty_results():
    def opener(req, timeout):
        raise HTTPError(req.full_url, 404, "Not Found", {}, None)
    with pytest.raises(PublicHtmlUnavailable, match=r"HTTP 404"):
        search_catalog_html("A Normal Game", "home", opener=opener)


def test_provider_error_retains_http_reason_but_no_secrets():
    def blocked(*args):
        raise PublicHtmlUnavailable("HTTP 403")
    result = lookup_title(
        "Stardew Valley",
        catalog_search=blocked,
        engine_search=lambda *args: [],
        external_search=lambda *args: [],
        meta_search=lambda *_: [],
        rss_search=lambda *_: [],
    )
    errors = [p for p in result.providers if p["provider"].startswith("dlsite_")]
    assert errors
    assert all(p["detail"] == "HTTP 403" for p in errors)
    assert any("HTTP 403" in w for w in result.warnings)
