"""v0.11.7: synthetic regression for strict no-API standalone search."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.dlsite_detector.filename_only import identify_filename
from experiments.dlsite_detector.filename_web_search import search_one_title, worker_main
from experiments.dlsite_detector.no_api_html import (
    PublicHtmlUnavailable, fetch_dlsite_html, fetch_steam_html,
    search_public_html,
)


class Response:
    def __init__(self, url, text, kind="text/html"):
        self.url = url
        self.stream = BytesIO(text.encode("utf-8"))
        self.headers = {"Content-Type": kind}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, number):
        return self.stream.read(number)

    def geturl(self):
        return self.url


def test_html_ddg_results_without_json_api():
    seen = []
    def opener(req, timeout):
        seen.append(req.full_url)
        return Response(req.full_url,
            '<div><a class="result__a" href="https://example.itch.io/my-game">My Game by Maker</a></div>')
    rows = search_public_html("My Game", "ddg_html", opener=opener)
    assert rows[0]["href"] == "https://example.itch.io/my-game"
    assert rows[0]["title"] == "My Game by Maker"
    assert "html.duckduckgo.com/html/" in seen[0]
    assert "/api/" not in seen[0]


def test_html_ddg_redirect_unwrap_and_nonresult_rejected():
    def opener(req, timeout):
        return Response(req.full_url, (
            '<a class="menu" href="https://example.org/other">Menu</a>'
            '<a class="result__a" href="https://duckduckgo.com/l/?uddg='
            'https%3A%2F%2Fmaker.itch.io%2Fmy-game">My Game</a>'
        ))
    result = search_public_html("My Game", "ddg_html", opener=opener)
    assert len(result) == 1
    assert result[0]["href"] == "https://maker.itch.io/my-game"


def test_itch_store_page_only_not_external_navigation():
    def opener(req, timeout):
        return Response(req.full_url, (
            '<a href="https://itch.io/login">Sign in</a>'
            '<a href="https://maker.itch.io/my-game">My Game by Maker</a>'
            '<a href="https://bad.example.net/">My Game Reviews</a>'
        ))
    rows = search_public_html("My Game", "itch_html", opener=opener)
    assert len(rows) == 1
    assert rows[0]["href"] == "https://maker.itch.io/my-game"


def test_mojeek_html_navigation_filtered_by_ranker():
    def opener(req, timeout):
        return Response(req.full_url,
            '<a href="https://www.mojeek.com/about">About</a>'
            '<a class="result-header" href="https://maker.itch.io/my-game">My Game</a>')
    rows = search_public_html("My Game", "mojeek_html", opener=opener)
    assert len(rows) == 1
    assert rows[0]["title"] == "My Game"


def test_product_html_code_and_title_verified_without_json_endpoint():
    seen = []
    def opener(req, timeout):
        seen.append(req.full_url)
        return Response(req.full_url, (
            '<html><head><meta property="og:title" content="My Example Game - DLsite"></head>'
            '<body><h1>My Example Game</h1><div>RJ123456</div></body></html>'
        ))
    p = fetch_dlsite_html("RJ123456", opener=opener)
    assert p.code == "RJ123456"
    assert p.title == "My Example Game"
    assert p.work_type == ""
    assert seen == ["https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"]


def test_dlsite_html_other_code_rejected():
    def opener(req, timeout):
        return Response(req.full_url,
            '<meta property="og:title" content="Other Game - DLsite"><p>RJ777777</p>')
    assert fetch_dlsite_html("RJ123456", opener=opener) is None


def test_steam_public_app_page_without_appdetails():
    seen = []
    def opener(req, timeout):
        seen.append(req.full_url)
        return Response(req.full_url, '<meta property="og:title" content="My Example Game on Steam">')
    p = fetch_steam_html("123456", opener=opener)
    assert p.app_id == "123456"
    assert p.title == "My Example Game"
    assert p.item_type == "unknown"
    assert "/api/appdetails" not in seen[0]


def test_captcha_is_error_not_empty_results():
    def opener(req, timeout):
        return Response(req.full_url, "<html><body>Verify you are human</body></html>")
    with pytest.raises(PublicHtmlUnavailable, match="CAPTCHA"):
        search_public_html("My Game", "ddg_html", opener=opener)


def test_strict_search_never_invokes_old_json_provider():
    calls = []
    def public_search(title, source):
        calls.append(source)
        return [{"title": "My Example Game by Maker",
                 "href": "https://maker.itch.io/my-example-game"}]
    with (
        patch("experiments.dlsite_detector.filename_web_search.search_public_html", side_effect=public_search),
        patch("experiments.dlsite_detector.filename_web_search.serper_google_search", side_effect=AssertionError("Serper forbidden")),
        patch("experiments.dlsite_detector.pipeline.fast_web_search", side_effect=AssertionError("DDGS forbidden")),
    ):
        providers = []
        rows = search_one_title("My Example Game", providers, no_api=True)
    assert calls == ["ddg_html"]
    assert len(rows) == 1
    assert providers[0]["provider"] == "ddg_html"


def test_explicit_code_in_strict_mode_uses_only_html():
    from experiments.dlsite_detector.detector import Product
    fake = Product("RJ123456", "My Example Game", "", "maniax",
                   "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html")
    with (
        patch("experiments.dlsite_detector.filename_only.fetch_dlsite_html", return_value=fake) as html,
        patch("experiments.dlsite_detector.filename_only.fetch_product", side_effect=AssertionError("JSON API forbidden")),
        patch("experiments.dlsite_detector.filename_only.fetch_steam_product", side_effect=AssertionError("Steam API forbidden")),
    ):
        result = identify_filename("My Example Game [RJ123456].zip", no_api=True)
    assert html.call_count == 1
    assert result.status == "catalog_found"
    assert result.candidates[0].source == "official_html"
    assert all(e == "" for e in result.errors)


def test_worker_no_api_flag_skips_all_json_services(tmp_path: Path):
    inbound = tmp_path / "input.json"
    outbound = tmp_path / "output.json"
    inbound.write_text(json.dumps({"query": "My Example Game", "no_api": True}),
                       encoding="utf-8")
    with (
        patch("experiments.dlsite_detector.filename_web_search.search_public_html",
              return_value=[{"title": "My Example Game by Maker",
                             "href": "https://maker.itch.io/my-example-game"}]) as html,
        patch("experiments.dlsite_detector.filename_web_search.serper_google_search",
              side_effect=AssertionError("Serper forbidden")),
    ):
        assert worker_main(str(inbound), str(outbound)) == 0
    assert html.called
    result = json.loads(outbound.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["providers"][0]["provider"] == "ddg_html"


def test_html_search_has_fixed_allowed_provider_list():
    with pytest.raises(ValueError):
        search_public_html("My Game", "http://example.com/api")


def test_html_only_steam_search_keeps_title_when_kind_unverified():
    from experiments.dlsite_detector.filename_web_search import SearchRows
    from experiments.dlsite_detector.steam_client import SteamProduct
    rows = SearchRows([{
        "title": "My Example Game on Steam",
        "href": "https://store.steampowered.com/app/123456/My_Example_Game/",
        "body": "Game",
    }], [{"provider": "steam_html", "state": "relevant"}])
    product = SteamProduct("123456", "My Example Game", "unknown",
                           "https://store.steampowered.com/app/123456/")
    with (
        patch("experiments.dlsite_detector.filename_only.isolated_web_search",
              return_value=rows),
        patch("experiments.dlsite_detector.filename_only.fetch_steam_html",
              return_value=product) as html,
        patch("experiments.dlsite_detector.filename_only.fetch_steam_product",
              side_effect=AssertionError("Steam JSON API forbidden")),
    ):
        result = identify_filename("My Example Game [v1.1].zip", no_api=True)
    assert html.called
    assert result.status == "likely"
    assert result.best_title == "My Example Game"
    assert result.candidates[0].source == "official_html"
    assert result.rejected_pages == ()
    assert "미검증" in result.candidates[0].notes


def test_dlsite_agegate_is_not_accepted_as_work():
    def opener(req, timeout):
        return Response(req.full_url, (
            '<meta property="og:title" content="Age Verification - DLsite">'
            '<body>RJ123456</body>'
        ))
    assert fetch_dlsite_html("RJ123456", opener=opener) is None
