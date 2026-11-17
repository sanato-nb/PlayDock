"""게임 식별 기능 정밀 테스트: Steam 원본, 파일 유형, 다국어·동명이작, 오류 격리."""
from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
import json
import zipfile

import pytest

from experiments.dlsite_detector.identity_hints import extract_hints
from experiments.dlsite_detector.search_terms import cleaned_search_title
from experiments.dlsite_detector.steam_client import (
    SteamLookupUnavailable, SteamProduct, fetch_steam_product, parse_steam_appdetails,
)
from experiments.dlsite_detector.enhanced_search import (
    enhanced_classify_game, _steam_url_id,
)
from experiments.dlsite_detector.pipeline import SearchDecision, WebEvidence
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.review_store import ReviewStore


def product(appid="1621540", name="Spooky Milk Life", kind="game"):
    return SteamProduct(
        appid, name, kind, f"https://store.steampowered.com/app/{appid}/",
        "Example Developer", "Example Publisher", "2025-01-01",
    )


def base(query, **kwargs):
    return SearchDecision(
        "lookup_unavailable", query, reason="아직 확인되지 않은 작품", web_checked=True,
    )


def hit(url, title="Game"):
    return WebEvidence(title, url, "store.steampowered.com", True, True, True)


def test_steam_and_dlsite_id_extract_separately():
    h = extract_hints("Eliminator 카에데씨 [v1.2] [RJ209760·Steam 1122040].7z")
    assert h.dlsite_codes == ("RJ209760",)
    assert h.steam_app_ids == ("1122040",)
    assert cleaned_search_title("Eliminator 카에데씨 [v1.2] [RJ209760·Steam 1122040].7z") == "Eliminator 카에데씨"


def test_steam_id_filename_lookup_confirms_game_without_web_search():
    called = []
    result = enhanced_classify_game(
        "Spooky Milk Life [Steam 1621540].7z",
        classifier=lambda *_a, **_kw: pytest.fail("Steam 작품 일치 시 일반 검색 불필요"),
        steam_fetcher=lambda appid: called.append(appid) or product(),
    )
    assert called == ["1621540"]
    assert result.status == "platform_confirmed_game"
    assert result.proposed_title == "Spooky Milk Life"
    assert result.source_platform == "steam"
    assert result.source_id == "1621540"
    assert result.source_url == "https://store.steampowered.com/app/1621540/"
    assert "압축파일의 실제 내용까지" in result.reason


def test_wrong_steam_app_id_does_not_confirm_game():
    result = enhanced_classify_game(
        "Spooky Milk Life [Steam 1621540]",
        classifier=base,
        steam_fetcher=lambda _: product(appid="9999999"),
    )
    assert result.status != "platform_confirmed_game"


def test_wrong_steam_title_requires_review():
    result = enhanced_classify_game(
        "Completely Different Game [Steam 1621540]",
        classifier=lambda *_a, **_kw: pytest.fail("원본 Steam ID 정보가 있으면 수동 검토"),
        steam_fetcher=lambda _: product(),
    )
    assert result.status == "internet_candidate"
    assert result.proposed_title == "Spooky Milk Life"
    assert "게임 이름이 다릅니다" in result.reason


@pytest.mark.parametrize("kind", ("dlc", "music", "demo", "video"))
def test_steam_non_game_product_types_never_confirmed(kind):
    result = enhanced_classify_game(
        "Spooky Milk Life [Steam 1621540]",
        classifier=base, steam_fetcher=lambda _: product(kind=kind),
    )
    assert result.status == "internet_candidate"


@pytest.mark.parametrize("filename,expected", (
    ("Craft to Exile 2 [Server v1.1.3].zip", "server_package_candidate"),
    ("SummertimeSaga [한국어 패치 Fix2].zip", "patch_candidate"),
    ("Game [DLC 2.0.1].7z", "dlc_candidate"),
    ("Game [한글패치·본편 포함].zip", "game_with_patch_candidate"),
    ("Fate Empire of Dirt + Made in Heaven.7z", "bundle_candidate"),
    ("Spooky Milk Life [Steam 1621540].7z", "unknown"),
))
def test_archive_kind_is_separate_from_game_identity(filename, expected):
    assert extract_hints(filename).archive_kind == expected


@pytest.mark.parametrize("filename", (
    "Craft to Exile 2 [Server v1.1.3].zip",
    "My Game [DLC 2.0.1].zip",
    "My Game [한국어 패치 Fix2].zip",
))
def test_stored_steam_game_does_not_convert_patch_server_or_dlc_to_base(filename):
    title = "Craft to Exile 2" if filename.startswith("Craft") else "My Game"
    result = enhanced_classify_game(
        filename,
        classifier=lambda *_a, **_kw: SearchDecision("confirmed_game", title, proposed_title=title),
        steam_fetcher=lambda _: pytest.fail("no Steam ID"),
    )
    assert result.status == "internet_candidate"
    assert result.archive_kind != "unknown"


def test_steam_id_in_server_package_needs_review():
    result = enhanced_classify_game(
        "Craft to Exile 2 [Server v1.1.3] [Steam 12345]",
        classifier=base, steam_fetcher=lambda _: product("12345", "Craft to Exile 2"),
    )
    assert result.status == "internet_candidate"
    assert result.archive_kind == "server_package_candidate"


def test_steam_product_response_rejects_wrong_id_and_bad_types():
    good = {"1621540": {"success": True, "data": {
        "steam_appid": 1621540, "name": "Spooky Milk Life",
        "type": "game", "developers": ["Creator"], "publishers": ["Publisher"],
        "release_date": {"date": "Jan 1, 2025"},
    }}}
    r = parse_steam_appdetails(good, "1621540")
    assert r.title == "Spooky Milk Life"
    assert r.developer == "Creator"
    assert r.release_date == "Jan 1, 2025"
    good["1621540"]["data"]["steam_appid"] = 1
    assert parse_steam_appdetails(good, "1621540") is None
    with pytest.raises(ValueError):
        parse_steam_appdetails(good, "broken")


def test_steam_lookup_only_uses_bounded_exact_id_https():
    class Resp(BytesIO):
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.close()
    queried = []
    def opener(req, *, timeout):
        queried.append(req.full_url)
        return Resp(json.dumps({
            "1621540": {"success": True, "data": {
                "steam_appid": 1621540, "name": "Spooky Milk Life", "type": "game",
            }}
        }).encode())
    assert fetch_steam_product("1621540", opener=opener).title == "Spooky Milk Life"
    assert len(queried) == 1
    assert queried[0].startswith("https://store.steampowered.com/api/appdetails?appids=1621540")
    with pytest.raises(ValueError):
        fetch_steam_product("1621540&appids=100", opener=opener)
    assert len(queried) == 1


def test_steam_errors_do_not_become_negative_proof():
    def bad(req, *, timeout):
        raise HTTPError(req.full_url, 429, "rate limited", {}, None)
    with pytest.raises(SteamLookupUnavailable):
        fetch_steam_product("1621540", opener=bad)
    final = enhanced_classify_game(
        "Spooky Milk Life [Steam 1621540]",
        classifier=base,
        steam_fetcher=lambda _: (_ for _ in ()).throw(SteamLookupUnavailable("blocked")),
    )
    assert final.status == "lookup_unavailable"
    assert "Steam 원본 조회 실패" in final.reason


def test_official_steam_url_parse_defends_against_lookalikes():
    assert _steam_url_id("https://store.steampowered.com/app/1621540/example") == "1621540"
    for url in (
        "http://store.steampowered.com/app/1621540/",
        "https://store.steampowered.com.evil.net/app/1621540/",
        "https://example.org/?next=https://store.steampowered.com/app/1621540",
        "https://user:pass@store.steampowered.com/app/1621540",
        "https://store.steampowered.com/bundle/1621540/",
    ):
        assert _steam_url_id(url) == ""


def test_official_steam_page_from_web_result_is_verified_before_candidate():
    result = enhanced_classify_game(
        "Spooky Milk Life.zip",
        classifier=lambda name, **kw: SearchDecision(
            "lookup_unavailable", name, web_checked=True,
            evidence=(hit("https://store.steampowered.com/app/1621540/"),),
        ),
        steam_fetcher=lambda _: product(),
    )
    assert result.status == "internet_candidate"
    assert result.source_id == "1621540"
    assert "Steam 상품 원본" in result.reason


def test_web_snippet_with_wrong_title_not_promoted_even_if_steam_page_exists():
    result = enhanced_classify_game(
        "Spooky Milk Life.zip",
        classifier=lambda name, **kw: SearchDecision(
            "internet_candidate", name, web_checked=True,
            evidence=(hit("https://store.steampowered.com/app/1621540/"),),
        ),
        steam_fetcher=lambda _: product(name="Other Game"),
    )
    assert result.status == "internet_candidate"
    assert result.source_id == ""


def test_alias_search_is_bounded_and_never_auto_confirmed():
    queried = []
    def classify(q, **kwargs):
        queried.append(q)
        if q == "Giant Treasure":
            return SearchDecision("internet_confirmed_game", q, proposed_title="Giant Treasure")
        return base(q)
    result = enhanced_classify_game(
        "거인의 비보 (Giant Treasure) [v1.8].7z",
        classifier=classify,
        steam_fetcher=lambda _: pytest.fail("no Steam ID"),
    )
    assert result.status == "internet_candidate"
    assert result.proposed_title == "Giant Treasure"
    assert queried == ["거인의 비보 (Giant Treasure) [v1.8].7z", "Giant Treasure"]


def test_same_game_sequel_is_not_accepted_as_alias():
    result = enhanced_classify_game("Demo 2", classifier=base)
    assert result.status == "lookup_unavailable"


def test_existing_archive_flow_uses_enhanced_lookup_without_reading_members(tmp_path, monkeypatch):
    # 실행 명령에서 기본 검색기가 바뀌더라도 원본 파일 읽기는 1차 미확인 시뿐.
    from experiments.dlsite_detector import archive_identity
    from experiments.dlsite_detector import enhanced_search
    assert archive_identity.identify_archive.__kwdefaults__["classifier"] is enhanced_search.enhanced_classify_game
    path = tmp_path / "A Game [Steam 1621540].zip"
    with zipfile.ZipFile(path, "w") as f:
        f.writestr("Not same game/Other.exe", b"demo")
    result = identify_archive(
        path,
        classifier=lambda _: SearchDecision(
            "platform_confirmed_game", "A Game", proposed_title="A Game",
            source_platform="steam", source_id="1621540",
        ),
        inspector=lambda _: pytest.fail("직접 확인 성공 후 내부 분석 금지"),
    )
    assert result.status == "confirmed_game" and result.stage == 1


def test_review_db_keeps_original_name_and_does_not_rename(tmp_path):
    store = ReviewStore(tmp_path / "experiment.db")
    store.add_game("one", "Spooky Milk Life [Steam 1621540]", "Spooky Milk Life [Steam 1621540].7z")
    decision = enhanced_classify_game(
        "Spooky Milk Life [Steam 1621540]",
        classifier=base,
        steam_fetcher=lambda _: product(),
    )
    store.save_search_result("one", decision)
    result = store.get_game("one")
    assert result["original_name"] == result["display_name"]
    assert result["classification"] == "platform_confirmed_game"
