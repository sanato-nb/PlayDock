"""PlayDock v0.11 이름·품번 단독 검색 회귀 테스트.

실제 게임 파일을 사용하지 않으며 ZIP/7z/RAR 내부를 읽지 않는다.
"""
from __future__ import annotations

import time
from unittest.mock import patch

from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.steam_client import SteamProduct
from experiments.dlsite_detector.filename_only import (
    VERSION, _BoundedGate, extract_filename_clues, identify_filename,
)


def product(code, title="Moon Valley", kind="ADV"):
    return Product(
        code, title, kind, "maniax",
        f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html",
    )


def fail_web(_):
    raise AssertionError("이 경우 제목 검색을 호출하면 안 됨")


def test_extract_archive_name_only_and_keep_series_number():
    clues = extract_filename_clues(
        r"C:\private\BUZAMA 2 [한국어] [RJ09999120].7z"
    )
    assert clues.archive_name == "BUZAMA 2 [한국어] [RJ09999120].7z"
    assert clues.game_name == "BUZAMA 2"
    assert clues.product_codes == ("RJ09999120",)
    assert clues.steam_ids == ()
    assert clues.source == "archive_filename_only"


def test_no_code_is_normal_and_version_removed():
    clues = extract_filename_clues("Agent Feminine [v0.4.7].zip")
    assert clues.game_name == "Agent Feminine"
    assert not clues.product_codes


def test_direct_official_id_success_requires_title_match_and_game_type():
    calls = []
    def lookup(code):
        calls.append(code)
        return product(code)
    r = identify_filename("Moon Valley [RJ09999119].zip",
                          dlsite_lookup=lookup, web_search=fail_web)
    assert r.status == "official_match"
    assert calls == ["RJ09999119"]
    assert r.lookups == ("DLsite RJ09999119",)
    assert r.to_dict()["archive_contents_inspected"] is False
    assert r.to_dict()["local_game_files_verified"] is False


def test_name_mismatch_stays_unresolved():
    r = identify_filename(
        "Moon Valley [RJ09999118].zip",
        dlsite_lookup=lambda code: product(code, "Unrelated World"),
        web_search=fail_web,
    )
    assert r.status == "likely"
    assert r.candidates[0].name_matches is False


def test_translation_patch_not_automatically_original_game():
    r = identify_filename(
        "Moon Valley [RJ09999117].7z",
        dlsite_lookup=lambda code: product(code, "【AI번역 패치】Moon Valley"),
        web_search=fail_web,
    )
    assert r.status == "likely"
    assert "번역 패치" in r.candidates[0].notes


def test_non_game_registered_code_is_not_game_identification():
    r = identify_filename(
        "Moon Valley [RJ09999116].zip",
        dlsite_lookup=lambda code: product(code, "Moon Valley", "SOU"),
        web_search=fail_web,
    )
    assert r.status == "likely"
    assert r.candidates[0].work_type == "SOU"


def test_two_official_product_codes_remain_multiple():
    r = identify_filename(
        "Moon Valley [RJ09999115, RJ09999114].zip",
        dlsite_lookup=lambda code: product(code),
        web_search=fail_web,
    )
    assert len(r.candidates) == 2
    assert r.status == "multiple"
    assert r.is_unresolved


def test_official_catalog_code_only_does_not_certify_game_filename():
    r = identify_filename(
        "RJ09999113.zip", dlsite_lookup=lambda code: product(code),
        web_search=fail_web,
    )
    assert r.extracted.game_name == ""
    assert r.status == "likely"


def test_lookup_returning_different_id_rejected():
    r = identify_filename(
        "Moon Valley [RJ09999112].zip",
        dlsite_lookup=lambda code: product("RJ09999111"),
        web_search=fail_web,
    )
    assert r.status == "search_error"
    assert not r.candidates


def test_no_code_one_web_search_and_no_result_means_unidentified():
    seen = []
    def search(query):
        seen.append(query)
        return []
    r = identify_filename("BunnyHero [v0.5.2].zip", web_search=search)
    assert r.status == "unidentified"
    assert seen == ["BunnyHero"]
    assert r.lookups == ("제목 BunnyHero",)


def test_no_code_web_search_failure_distinct_from_missing_game():
    r = identify_filename(
        "BunnyHero.zip", web_search=lambda _: (_ for _ in ()).throw(RuntimeError())
    )
    assert r.status == "search_error"
    assert r.errors
    assert r.is_unresolved


def test_steam_id_direct_official_product_lookup():
    r = identify_filename(
        "Moon Valley [Steam 1234567].zip", web_search=fail_web,
        steam_lookup=lambda sid: SteamProduct(
            sid, "Moon Valley", "game",
            f"https://store.steampowered.com/app/{sid}/"
        ),
    )
    assert r.status == "official_match"
    assert r.product_id == "1234567"
    assert len(r.candidates) == 1


def test_steam_mismatch_is_not_confirmed():
    r = identify_filename(
        "Moon Valley [Steam 1234568].zip", web_search=fail_web,
        steam_lookup=lambda sid: SteamProduct(
            sid, "Other Story", "game",
            f"https://store.steampowered.com/app/{sid}/"
        ),
    )
    assert r.status == "likely"


def test_no_code_verified_steam_listing_through_search():
    seen = []
    def fake_web(q):
        seen.append(q)
        return [{
            "href": "https://store.steampowered.com/app/1234567/Moon_Valley/",
            "title": "Moon Valley on Steam",
            "body": "Game on Steam"
        }]
    r = identify_filename(
        "Moon Valley.zip", web_search=fake_web,
        steam_lookup=lambda sid: SteamProduct(
            sid, "Moon Valley", "game",
            f"https://store.steampowered.com/app/{sid}/"
        ),
    )
    assert seen == ["Moon Valley"]
    assert r.status == "official_match"
    assert len(r.candidates) == 1


def test_itch_store_search_is_candidate_not_verified():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "href": "https://author.itch.io/moon-valley",
        "title": "Moon Valley - itch.io",
        "body": "Game",
    }])
    assert r.status == "likely"
    assert r.candidates[0].platform == "itch.io"
    assert r.candidates[0].source == "search_result"


def test_itch_comment_is_not_game_page():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "href": "https://author.itch.io/moon-valley/comments",
        "title": "Moon Valley - itch.io",
        "body": "Game",
    }])
    assert r.status == "unidentified"
    assert not r.candidates


def test_offline_never_opens_archive_or_connects():
    with patch("builtins.open", side_effect=AssertionError("file open")):
        r = identify_filename(
            "Moon Valley [RJ09999110].zip", online=False,
            dlsite_lookup=lambda _: fail_web(""), web_search=fail_web,
        )
    assert r.status == "unidentified"
    assert r.extracted.product_codes == ("RJ09999110",)
    assert r.lookups == ("오프라인: 외부 검색 미실행",)


def test_filename_only_does_not_stat_or_open_archive():
    with patch("pathlib.Path.open", side_effect=AssertionError("archive opened")):
        with patch("pathlib.Path.stat", side_effect=AssertionError("archive stat")):
            r = identify_filename(
                "DoesNotExist [RJ09999109].zip",
                dlsite_lookup=lambda code: product(code, "DoesNotExist"),
            )
    assert r.status == "official_match"


def test_lookup_timeout_is_bounded_and_subsequent_busy_request_does_not_spawn_more():
    gate = _BoundedGate()
    def slow():
        time.sleep(0.20)
        return 1
    begin = time.monotonic()
    try:
        gate.call(slow, timeout=0.03)
        assert False, "타임아웃 발생해야 함"
    except TimeoutError:
        pass
    assert time.monotonic() - begin < 0.15
    try:
        gate.call(lambda: 2, timeout=0.03)
        assert False, "기존 작업 동안 새 스레드 생성하지 않아야 함"
    except RuntimeError:
        pass
    time.sleep(0.22)
    assert gate.call(lambda: 3, timeout=0.1) == 3


def test_script_self_test_has_no_internet():
    from scripts.filename_identity_tester import self_test
    assert self_test() == 0


def test_version_is_filename_only_test():
    assert VERSION == "0.11-test"
