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
    assert r.status == "catalog_found"
    assert r.best_title == "Moon Valley"
    assert not r.is_unresolved
    assert r.to_dict()["local_game_files_verified"] is False


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
    assert VERSION == "0.11.2-test"



def test_korean_file_title_japanese_official_title_catalog_found():
    r = identify_filename(
        "미라와 이상한 연금술 [RJ09999108].zip",
        dlsite_lookup=lambda code: product(code, "ミラと不思議な錬金術"),
        web_search=fail_web,
    )
    assert r.status == "catalog_found"
    assert not r.candidates[0].name_matches
    assert r.product_id == "RJ09999108"
    assert r.is_unresolved is False


def test_unrelated_english_name_not_catalog_found():
    r = identify_filename(
        "Moon Valley [RJ09999107].zip",
        dlsite_lookup=lambda code: product(code, "Unrelated Story"),
        web_search=fail_web,
    )
    assert r.status == "likely"
    assert r.is_unresolved


def test_patch_and_non_game_not_promoted_to_catalog_found():
    for title, kind in (("【AI번역 패치】Moon Valley", "ADV"),
                        ("Moon Valley", "SOU")):
        r = identify_filename(
            "RJ09999106.zip",
            dlsite_lookup=lambda code, title=title, kind=kind: product(
                code, title, kind
            ),
            web_search=fail_web,
        )
        assert r.status == "likely", (title, kind, r)


def test_bing_rss_parsing_and_untrusted_html_not_mistaken_for_no_results():
    from io import BytesIO
    from experiments.dlsite_detector.filename_web_search import (
        SearchWorkerError, bing_rss_search,
    )
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><item>
    <title>Moon Valley - Steam</title>
    <link>https://store.steampowered.com/app/1234567/</link>
    <description>Test game</description>
    </item><item>
    <title>Not HTTPS</title><link>http://notsecure.example/a</link>
    </item></channel></rss>"""
    found = bing_rss_search("Moon Valley", opener=lambda req, timeout: BytesIO(xml))
    assert len(found) == 1
    assert found[0]["href"] == "https://store.steampowered.com/app/1234567/"
    try:
        bing_rss_search("Moon Valley", opener=lambda req, timeout: BytesIO(
            b"<html><body>Bot challenge</body></html>"
        ))
        assert False, "HTML content must be considered provider error"
    except SearchWorkerError:
        pass


def test_child_timeout_does_not_poison_next_title_lookup():
    import subprocess
    from pathlib import Path
    from experiments.dlsite_detector.filename_web_search import (
        SearchWorkerTimeout, isolated_web_search
    )
    count = []
    def mocked_subprocess(cmd, **options):
        count.append(cmd)
        if len(count) == 1:
            raise subprocess.TimeoutExpired(cmd, timeout=options["timeout"])
        assert cmd[1:3] == ["-m", "scripts.filename_identity_tester"]
        Path(cmd[-1]).write_text(
            '{"ok":true,"rows":[{"title":"Moon Valley","href":'
            '"https://store.steampowered.com/app/1234567/"}]}',
            encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 0)
    try:
        isolated_web_search("Moon Valley", timeout=0.5,
                            runner=mocked_subprocess)
        assert False, "worker timeout expected"
    except SearchWorkerTimeout:
        pass
    rows = isolated_web_search("Another Game", timeout=0.5,
                               runner=mocked_subprocess)
    assert rows and rows[0]["title"] == "Moon Valley"
    assert len(count) == 2


def test_search_worker_uses_only_extracted_title(tmp_path, monkeypatch):
    from experiments.dlsite_detector.filename_web_search import worker_main
    from experiments.dlsite_detector import filename_web_search
    import json
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text('{"query":"Moon Valley"}', encoding="utf-8")
    monkeypatch.setattr(filename_web_search, "search_one_title",
                        lambda title: [{"title": title,
                                        "href": "https://example.com/game"}])
    assert worker_main(str(input_path), str(output_path)) == 0
    obj = json.loads(output_path.read_text(encoding="utf-8"))
    assert obj["ok"] and obj["rows"][0]["title"] == "Moon Valley"


def test_default_title_backend_is_isolated(monkeypatch):
    from experiments.dlsite_detector import filename_only as engine
    called = []
    def fake_isolated(q):
        called.append(q)
        return []
    monkeypatch.setattr(engine, "isolated_web_search", fake_isolated)
    r = identify_filename("NoProductIdGame.zip")
    assert r.status == "unidentified"
    assert called == ["NoProductIdGame"]
    assert not any("LookupBusy" in e for e in r.errors)



def test_web_game_article_is_hint_not_official_confirmation():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "href": "https://game-news.example.org/reviews/moon-valley",
        "title": "Moon Valley - Gameplay impressions",
        "body": "Review of a new PC game",
    }])
    assert r.status == "web_candidate"
    assert r.candidates[0].source == "web_search"
    assert r.is_unresolved
    assert r.to_dict()["web_raw_results"][0]["title"].startswith("Moon Valley")
    assert len(r.web_evidence) == 1


def test_community_game_page_is_web_hint_not_confirmed():
    r = identify_filename("6월의 너와 나.zip", web_search=lambda _: [{
        "href": "https://kone.gg/s/somisoft/story",
        "title": "[복구요청] 6월의 너와 나 - 소미소프트 | Kone",
        "body": "자료 한글명 or 원어명 6월의 너와 나",
    }])
    assert r.status == "web_candidate"
    assert r.is_unresolved
    assert r.best_title == "6월의 너와 나"


def test_unrelated_web_result_recorded_but_not_a_candidate():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "href": "https://cooking.example.org/blog/moon-valley",
        "title": "Moon Valley - Summer Recipes",
        "body": "Breakfast recipes, no games discussed",
    }])
    assert r.status == "unidentified"
    assert len(r.web_raw_results) == 1
    assert "1건" in r.reason


def test_no_results_report_zero_distinctly_from_filtered_results():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [])
    assert r.status == "unidentified"
    assert not r.web_raw_results
    assert "0건" in r.reason


def test_search_provider_telemetry_survives_to_json():
    from experiments.dlsite_detector.filename_web_search import SearchRows
    def fake(_):
        return SearchRows([], [
            {"provider":"bing_rss","state":"ok","result_count":0,"seconds":0.1},
            {"provider":"ddgs","state":"ok","result_count":0,"seconds":0.1},
        ])
    r = identify_filename("Moon Valley.zip", web_search=fake)
    assert len(r.search_providers) == 2
    assert r.to_dict()["search_providers"][0]["provider"] == "bing_rss"
