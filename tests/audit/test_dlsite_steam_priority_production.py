"""DLsite → Steam 공식 HTML 순차 확인/최종 제외 정책 검증."""
import pytest

from integrations.official_lookup.code_only import (
    InputItem, check, codes_in, steam_ids_in,
)
from integrations.official_lookup.detector import Product
from integrations.official_lookup.steam_client import SteamProduct


def dl(code, *, returned=None):
    return Product(returned or code, "DL Work", "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def steam(appid, *, returned=None, url=None, kind="game"):
    return SteamProduct(returned or appid, "Steam Work", kind,
                        url or f"https://store.steampowered.com/app/{appid}/")


def never(_):
    raise AssertionError("건너뛰어야 하는 사이트를 호출함")


@pytest.mark.parametrize("label,expected", [
    ("Test [Steam 1091500].zip", ("1091500",)),
    ("Test [SteamAppID=1091500].7z", ("1091500",)),
    ("Test [Steam ID: 1091500].rar", ("1091500",)),
    ("Test AppID#1091500.zip", ("1091500",)),
    ("STEAM_APP_ID_1091500", ("1091500",)),
    ("Test Steam-1091500 + SteamAppID:1091500.7z", ("1091500",)),
    ("Test [v1.1091500] [Build 1091500].zip", ()),
    ("Test 1091500.zip", ()),
    ("RJ123456 [DLC 1091500].zip", ()),
])
def test_explicit_steam_id_only(label, expected):
    assert steam_ids_in(label) == expected


def test_manual_plain_numeric_is_steam_but_filename_numeric_is_not():
    assert steam_ids_in("1091500", manual=True) == ("1091500",)
    assert steam_ids_in("1091500", manual=False) == ()
    item = InputItem("1091500", "manual")
    result = check(item, fetcher=never, steam_fetcher=lambda a: steam(a))
    assert result.status == "confirmed"
    assert result.selected_store == "steam"
    assert result.attempted_stores == ("steam",)


def test_dlsite_first_when_both_ids_and_skip_steam_on_success():
    result = check(
        InputItem("Game [RJ123456] [Steam 1091500].zip", "archive"),
        fetcher=lambda code: dl(code),
        steam_fetcher=never)
    assert result.status == "confirmed"
    assert result.selected_store == "dlsite"
    assert result.attempted_stores == ("dlsite",)
    assert [row.store for row in result.works] == ["dlsite"]
    assert "Steam 조회는 생략" in result.warnings[-1]


def test_failed_dlsite_uses_steam_and_records_both_attempts():
    calls = []
    def dl_failed(code):
        calls.append("DL:" + code)
        return None
    def steam_ok(code):
        calls.append("STEAM:" + code)
        return steam(code)
    result = check(
        InputItem("Game [RJ123456] [SteamAppID 1091500].zip", "archive"),
        fetcher=dl_failed, steam_fetcher=steam_ok)
    assert calls == ["DL:RJ123456", "STEAM:1091500"]
    assert result.status == "confirmed"
    assert result.selected_store == "steam"
    assert result.attempted_stores == ("dlsite", "steam")
    assert [row.status for row in result.works] == ["unavailable", "verified"]
    assert [row.store for row in result.works] == ["dlsite", "steam"]
    assert "Steam 확인 결과" in result.warnings[-1]


def test_dlsite_partial_success_still_has_priority_over_steam():
    def dl_partial(code):
        return dl(code) if code == "RJ123456" else None
    result = check(
        InputItem("Game [RJ123456 RJ654321 Steam 1091500].zip", "archive"),
        fetcher=dl_partial, steam_fetcher=never)
    assert result.status == "partial"
    assert result.selected_store == "dlsite"
    assert result.attempted_stores == ("dlsite",)
    assert len(result.works) == 2


def test_steam_direct_when_dl_code_absent():
    result = check(
        InputItem("Game Steam 1091500.zip", "archive"),
        fetcher=never, steam_fetcher=lambda code: steam(code))
    assert result.status == "confirmed"
    assert result.selected_store == "steam"
    assert [row.code for row in result.works] == ["1091500"]


def test_both_failed_final_excluded_not_called_unregistered():
    result = check(
        InputItem("Game RJ123456 Steam 1091500.zip", "archive"),
        fetcher=lambda code: None, steam_fetcher=lambda code: None)
    assert result.status == "excluded"
    assert result.selected_store == ""
    assert result.attempted_stores == ("dlsite", "steam")
    assert any("미등록 판정은 아닙니다" in msg for msg in result.warnings)


def test_no_id_excluded_and_zero_http_requests():
    result = check(InputItem("Project Dungeon v1.03.zip", "archive"),
                   fetcher=never, steam_fetcher=never)
    assert result.status == "excluded"
    assert result.attempted_stores == ()
    assert len(result.works) == 0


def test_only_dl_code_unavailable_is_excluded():
    result = check(
        InputItem("RJ123456.7z", "archive"),
        fetcher=lambda code: None, steam_fetcher=never)
    assert result.status == "excluded"
    assert result.attempted_stores == ("dlsite",)


def test_bad_steam_product_id_is_not_accepted():
    result = check(InputItem("Steam 1091500.zip", "archive"),
                   fetcher=never,
                   steam_fetcher=lambda code: steam(code, returned="222222"))
    assert result.status == "excluded"


@pytest.mark.parametrize("url", [
    "https://malicious.example/app/1091500/",
    "https://store.steampowered.com.evil.example/app/1091500/",
    "https://store.steampowered.com/app/222222/",
    "http://store.steampowered.com/app/1091500/",
    "https://user@store.steampowered.com/app/1091500/",
])
def test_steam_official_url_validation(url):
    result = check(InputItem("Steam 1091500.zip", "archive"),
                   fetcher=never, steam_fetcher=lambda code: steam(code, url=url))
    assert result.status == "excluded"


def test_steam_appid_reuses_cache_across_archive_files():
    calls = []
    def fetch(code):
        calls.append(code)
        return steam(code)
    cache = {}
    a = check(InputItem("a [Steam 1091500].7z", "archive"),
              fetcher=never, steam_fetcher=fetch, cache=cache)
    b = check(InputItem("b [SteamAppID=1091500].rar", "archive"),
              fetcher=never, steam_fetcher=fetch, cache=cache)
    assert calls == ["1091500"]
    assert a.works == b.works


def test_steam_dlc_type_is_not_labeled_as_a_confirmed_game():
    result = check(InputItem("Steam 1091500.zip", "archive"),
                   fetcher=never,
                   steam_fetcher=lambda code: steam(code, kind="dlc"))
    assert result.selected_store == "steam"
    assert result.works[0].category == "dlc"
    assert result.works[0].title == "Steam Work"
    # Status verifies store title, not whether it is game vs DLC.


def test_multiple_steam_ids_keep_each_separately():
    result = check(InputItem("Steam 1091500 + AppID 222222.zip", "archive"),
                   fetcher=never,
                   steam_fetcher=lambda code: steam(code) if code == "1091500" else None)
    assert result.status == "partial"
    assert len(result.works) == 2
    assert result.selected_store == "steam"



def test_steam_public_prefers_no_key_store_data_before_html():
    from integrations.official_lookup.code_only import fetch_steam_public
    called = []
    def public(code):
        called.append("public")
        return steam(code)
    def html(code):
        called.append("html")
        raise AssertionError("API success should skip HTML")
    result = fetch_steam_public("1091500", api_fetcher=public, html_fetcher=html)
    assert result and result.title == "Steam Work"
    assert called == ["public"]


def test_steam_public_falls_back_to_official_html_when_public_endpoint_blocked():
    from integrations.official_lookup.code_only import fetch_steam_public
    called = []
    def blocked(code):
        called.append("public")
        raise RuntimeError("HTTP 429")
    def html(code):
        called.append("html")
        return steam(code)
    result = fetch_steam_public("1091500", api_fetcher=blocked, html_fetcher=html)
    assert result and result.app_id == "1091500"
    assert called == ["public", "html"]
