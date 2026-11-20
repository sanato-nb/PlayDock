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
    assert r.status == "web_candidate"
    assert r.candidates[0].platform == "itch.io"
    assert r.candidates[0].source == "web_search"


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
    assert VERSION == "0.11.6-test"



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
                        lambda title, providers=None, **kwargs: [{"title": title,
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
        "body": "Breakfast, sugar, and fruit recipes",
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



def test_ddgs_article_only_continues_to_bing_for_storefront(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    seen = []
    monkeypatch.setattr(w, "bing_rss_search", lambda _: [{
        "title": "Moon Valley by Studio",
        "href": "https://studio.itch.io/moon-valley",
        "body": "PC game",
    }])
    def primary(q):
        seen.append(q)
        return [{
            "title": "Moon Valley - Gameplay Guide",
            "href": "https://game-review.example.org/moon-valley",
            "body": "PC game review",
        }]
    monkeypatch.setattr(pipeline, "fast_web_search", primary)
    trace = []
    rows = w.search_one_title("Moon Valley", trace)
    assert seen == ["Moon Valley"]
    assert rows[0]["href"] == "https://studio.itch.io/moon-valley"
    assert [x["provider"] for x in trace] == ["ddgs", "bing_rss"]
    assert trace[0]["relevant_count"] == 1
    assert trace[0]["strong_page_count"] == 0


def test_ddgs_irrelevant_falls_back_to_bing(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Canva Design", "href": "https://www.canva.com/",
        "body": "visual design",
    }])
    monkeypatch.setattr(w, "bing_rss_search", lambda _: [{
        "title": "Moon Valley - itch.io",
        "href": "https://author.itch.io/moon-valley",
        "body": "PC game",
    }])
    trace = []
    rows = w.search_one_title("Moon Valley", trace)
    assert len(rows) == 1
    assert [p["provider"] for p in trace] == ["ddgs", "bing_rss"]
    assert trace[0]["state"] == "irrelevant"
    assert trace[1]["relevant_count"] == 1


def test_ddgs_direct_game_page_skips_bing(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(w, "bing_rss_search", lambda _: (
        _ for _ in ()).throw(AssertionError("redundant Bing search")))
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Moon Valley by Author - itch.io",
        "href": "https://author.itch.io/moon-valley",
        "body": "Download game",
    }])
    trace = []
    result = w.search_one_title("Moon Valley", trace)
    assert len(result) == 1
    assert len(trace) == 1
    assert trace[0]["relevant_count"] == 1


def test_short_title_rec_store_is_web_hint_but_not_official():
    r = identify_filename("REC [v0.4.2.2].zip", web_search=lambda _: [{
        "title": "REC by moondev",
        "href": "https://moondev64.itch.io/rec",
        "body": "Play REC game on itch.io",
    }])
    assert r.status in {"web_candidate", "likely"}
    assert r.is_unresolved
    assert r.candidates[0].source in {"web_search", "search_result"}


def test_pasec_itch_page_recovered_as_unverified_candidate():
    r = identify_filename("PASEC [v2.2566].zip", web_search=lambda _: [{
        "title": "PASEC 1.5 Alpha by FalloutStar",
        "href": "https://falloutstar.itch.io/pasec",
        "body": "Download the game",
    }])
    assert r.status in {"web_candidate", "likely"}
    assert r.is_unresolved


def test_same_initial_word_is_not_full_game_title(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w
    assert w._row_quality("BunnyHero", {
        "title": "PAPAGO dashcam repair guide",
        "href": "https://car.example.org/reviews/dashcam",
        "body": "No video games here",
    }) == 0
    assert w._row_quality("Agent Feminine", {
        "title": "Agent meaning in dictionary",
        "href": "https://dictionary.example.org/agent",
        "body": "English words",
    }) == 0
    assert w._row_quality("REC", {
        "title": "Renewable energy certificate REC",
        "href": "https://energy.example.com/certificate",
        "body": "Electricity",
    }) == 0


def test_one_off_topic_provider_plus_ddgs_error_is_search_failure(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(w, "bing_rss_search", lambda _: [{
        "title": "Osaka Castle - Travel Guide",
        "href": "https://travel.example.org/castle",
        "body": "History of Japan",
    }])
    monkeypatch.setattr(pipeline, "fast_web_search",
                        lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    try:
        w.search_one_title("BUZAMA 2")
        assert False, "An unreliable query is not an actual negative lookup"
    except w.SearchWorkerError:
        pass



def test_developer_profile_and_unrelated_game_not_chosen():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [
        {
            "title": "moonvalley - itch.io",
            "href": "https://moonvalley.itch.io/",
            "body": "Game developer profile",
        },
        {
            "title": "Another Valley by moonvalley - itch.io",
            "href": "https://moonvalley.itch.io/another-valley",
            "body": "Game",
        },
    ])
    assert r.status == "unidentified"
    assert not r.candidates


def test_full_itch_game_page_beats_devlog_and_purchase_page():
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [
        {
            "title": "Devlog - Moon Valley by Author",
            "href": "https://author.itch.io/moon-valley/devlog/100/update",
            "body": "Game update",
        },
        {
            "title": "Purchase Moon Valley",
            "href": "https://author.itch.io/moon-valley/purchase",
            "body": "Game purchase",
        },
        {
            "title": "Moon Valley by Author",
            "href": "https://author.itch.io/moon-valley",
            "body": "Game",
        },
    ])
    assert r.status == "web_candidate"
    assert r.candidates[0].url == "https://author.itch.io/moon-valley"


def test_short_partial_steam_title_is_rejected():
    seen = []
    r = identify_filename(
        "NOR.zip",
        web_search=lambda _: [{
            "title": "Son of Nor on Steam",
            "href": "https://store.steampowered.com/app/264000/Son_of_Nor/",
            "body": "Adventure game",
        }],
        steam_lookup=lambda sid: seen.append(sid),
    )
    assert r.status == "unidentified"
    assert not seen


def test_chapter_hint_rejects_other_chapter_even_with_same_series_title():
    r = identify_filename(
        "Moon Valley [Chap.1].zip",
        web_search=lambda _: [
            {
                "title": "Moon Valley Chapter 3 by Author",
                "href": "https://author.itch.io/moon-valley-chapter-3",
                "body": "Game chapter",
            },
            {
                "title": "Moon Valley Chapter 1 - Guide",
                "href": "https://guide.example.org/games/moon-valley-chapter-1",
                "body": "Game chapter",
            },
        ],
    )
    assert r.status == "web_candidate"
    assert r.candidates[0].url.endswith("moon-valley-chapter-1")


def test_title_without_spaces_can_match_possessive_article():
    r = identify_filename(
        "AureliaStory.zip", web_search=lambda _: [{
            "title": "Update is now live! - Aurelia's Story by Author",
            "href": "https://author.itch.io/aurelias-story/devlog/100/news",
            "body": "Game development update",
        }],
    )
    assert r.status == "web_candidate"
    assert "aurelias-story" in r.candidates[0].url


def test_composite_title_matches_corresponding_page():
    r = identify_filename(
        "Moon Valley + Nightfall.zip", web_search=lambda _: [{
            "title": "Moon Valley - Nightfall - Official game site",
            "href": "https://studio.example.org/games/moon-valley-nightfall",
            "body": "A game created by Studio",
        }],
    )
    assert r.status == "web_candidate"
    assert "nightfall" in r.candidates[0].url


def test_steam_store_slug_and_official_api_both_match():
    calls = []
    r = identify_filename(
        "Moon Valley.zip",
        web_search=lambda _: [{
            "title": "Moon Valley on SteamSome other search titles merged",
            "href": "https://store.steampowered.com/app/1234567/Moon_Valley/",
            "body": "",
        }],
        steam_lookup=lambda sid: (
            calls.append(sid) or SteamProduct(
                sid, "Moon Valley", "game",
                f"https://store.steampowered.com/app/{sid}/"
            )
        ),
    )
    assert calls == ["1234567"]
    assert r.status == "official_match"
    assert r.candidates[0].product_id == "1234567"


def test_steam_store_wrong_official_title_is_never_accepted():
    r = identify_filename(
        "Moon Valley.zip",
        web_search=lambda _: [{
            "title": "Moon Valley on Steam",
            "href": "https://store.steampowered.com/app/1234567/Moon_Valley/",
            "body": "Game",
        }],
        steam_lookup=lambda sid: SteamProduct(
            sid, "Another Valley", "game",
            f"https://store.steampowered.com/app/{sid}/"
        ),
    )
    assert r.status == "unidentified"
    assert not r.candidates
    assert r.rejected_pages[0]["official_title"] == "Another Valley"


def test_worker_error_retains_provider_failure_details(tmp_path):
    from experiments.dlsite_detector.filename_web_search import (
        SearchWorkerError, isolated_web_search
    )
    import subprocess
    from pathlib import Path
    def run(cmd, **options):
        Path(cmd[-1]).write_text(
            '{"ok":false,"error":"SearchWorkerError",'
            '"details":"ddgs: RuntimeError: blocked",'
            '"providers":[{"provider":"ddgs","state":"error",'
            '"error":"RuntimeError: blocked","result_count":0}]}',
            encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 2)
    try:
        isolated_web_search("Moon Valley", runner=run)
        assert False, "worker error expected"
    except SearchWorkerError as exc:
        assert len(exc.providers) == 1
        assert exc.providers[0]["error"] == "RuntimeError: blocked"


def test_identify_error_preserves_providers_for_json():
    from experiments.dlsite_detector.filename_web_search import SearchWorkerError
    def fail(_):
        raise SearchWorkerError("provider is blocked", providers=[
            {"provider": "ddgs", "state": "error",
             "error": "connection blocked", "result_count": 0}
        ])
    r = identify_filename("Moon Valley.zip", web_search=fail)
    assert r.status == "search_error"
    assert r.search_providers[0]["provider"] == "ddgs"
    assert "provider is blocked" in r.errors[0]
    assert r.to_dict()["search_providers"][0]["error"] == "connection blocked"



def test_mismatching_dlsite_search_result_is_rejected_not_promoted(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    from experiments.dlsite_detector import detector
    fake_code = "RJ09999555"
    def fake_catalog(code, **kwargs):
        return product(code, "Different Game")
    monkeypatch.setattr(identity, "fetch_product", fake_catalog)
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "title": "Moon Valley - DLsite",
        "href": "https://www.dlsite.com/maniax/work/=/product_id/"
                + fake_code + ".html",
        "body": "RPG game",
    }])
    assert not r.candidates
    assert r.status == "unidentified"
    assert r.rejected_pages
    assert "다릅니다" in r.rejected_pages[0]["reason"]


def test_wrong_chapter_not_suggested_by_store_page():
    r = identify_filename("Garden Story [Chap.1].zip",
                          web_search=lambda _: [{
        "title": "Garden Story Chapter 2 by MoonDev",
        "href": "https://moondev.itch.io/garden-story-chapter-2",
        "body": "Game Chapter 2",
    }])
    assert r.status == "unidentified"
    assert not r.candidates


def test_multiple_possessive_names_are_not_hardcoded_to_story():
    from experiments.dlsite_detector.filename_page_rank import page_score
    rank = page_score(
        "AuroraDream", "Aurora's Dream by Creator",
        "https://author.itch.io/auroras-dream",
    )
    assert rank > 0



def test_serper_google_response_mapped_and_key_not_in_request_body():
    from io import BytesIO
    import json
    from experiments.dlsite_detector.serper_client import serper_google_search
    secret = "SUPERSECRET-TOKEN-DO-NOT-STORE"
    seen = []
    def opener(request, timeout):
        seen.append((request, timeout))
        return BytesIO(json.dumps({"organic": [
            {"title": "Goblin Nest by BadColor",
             "link": "https://badcolor.itch.io/goblin-nest",
             "snippet": "PC game from creator"},
            {"title": "insecure",
             "link": "http://bad.example.org/test",
             "snippet": "no"},
        ]}).encode())
    rows = serper_google_search("Goblin Nest", secret, opener=opener)
    assert len(rows) == 1
    assert rows[0]["href"] == "https://badcolor.itch.io/goblin-nest"
    request, timeout = seen[0]
    assert request.get_method() == "POST"
    assert request.get_header("X-api-key") == secret
    assert timeout <= 4.0
    assert json.loads(request.data)["q"] == '"Goblin Nest" game'
    assert secret not in request.full_url
    assert secret.encode() not in request.data
    assert secret not in str(rows)


def test_serper_invalid_key_http_error_sanitized():
    import urllib.error
    from experiments.dlsite_detector.serper_client import (
        serper_google_search, SerperSearchError
    )
    secret = "MY-PRIVATE-KEY"
    def invalid(_request, timeout):
        raise urllib.error.HTTPError(
            "https://google.serper.dev/search", 401,
            "MY-PRIVATE-KEY is unauthorized", None, None
        )
    try:
        serper_google_search("Moon Valley", secret, opener=invalid)
        assert False, "Serper invalid key should fail explicitly"
    except SerperSearchError as exc:
        assert "401" in str(exc)
        assert secret not in str(exc)


def test_serper_preferred_and_skips_ddgs_bing(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    calls = []
    def fake_google(title, key):
        calls.append(("google", title, key))
        return [{"title": "Goblin Nest by BadColor",
                 "href": "https://badcolor.itch.io/goblin-nest",
                 "body": "PC game"}]
    monkeypatch.setattr(w, "serper_google_search", fake_google)
    monkeypatch.setattr(pipeline, "fast_web_search",
                        lambda _: (_ for _ in ()).throw(
                            AssertionError("unexpected DDGS search")))
    monkeypatch.setattr(w, "bing_rss_search",
                        lambda _: (_ for _ in ()).throw(
                            AssertionError("unexpected Bing search")))
    trace = []
    rows = w.search_one_title("Goblin Nest", trace, serper_api_key="test-key")
    assert len(rows) == 1
    assert [x["provider"] for x in trace] == ["google_serper"]
    assert trace[0]["relevant_count"] == 1
    assert calls == [("google", "Goblin Nest", "test-key")]


def test_serper_bad_key_falls_back_to_ddgs_and_masks_key(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    secret = "KEY-MUST-BE-REDACTED"
    def bad_google(_title, _key):
        raise RuntimeError("bad token " + secret)
    monkeypatch.setattr(w, "serper_google_search", bad_google)
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Goblin Nest by BadColor",
        "href": "https://badcolor.itch.io/goblin-nest",
        "body": "PC game",
    }])
    trace = []
    rows = w.search_one_title("Goblin Nest", trace, serper_api_key=secret)
    assert len(rows) == 1
    assert [x["provider"] for x in trace] == ["google_serper", "ddgs"]
    assert trace[0]["state"] == "error"
    assert secret not in str(trace)
    assert "[REDACTED]" in str(trace)


def test_serper_irrelevant_falls_back_to_ddgs(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(w, "serper_google_search", lambda *_: [{
        "title": "Different Game",
        "href": "https://different.itch.io/game",
        "body": "PC game",
    }])
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Goblin Nest by BadColor",
        "href": "https://badcolor.itch.io/goblin-nest",
        "body": "PC game",
    }])
    trace = []
    rows = w.search_one_title("Goblin Nest", trace, serper_api_key="key")
    assert len(rows) == 1
    assert trace[0]["state"] == "irrelevant"
    assert trace[1]["provider"] == "ddgs"


def test_serper_not_used_without_explicit_key(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(w, "serper_google_search",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("Google requires opt-in")))
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Goblin Nest by BadColor",
        "href": "https://badcolor.itch.io/goblin-nest",
        "body": "PC game",
    }])
    assert w.search_one_title("Goblin Nest")[0]["title"].startswith("Goblin")


def test_worker_api_key_in_env_only_and_json_remains_private():
    import json
    import subprocess
    from pathlib import Path
    from experiments.dlsite_detector.filename_web_search import (
        isolated_web_search
    )
    secret = "DO-NOT-EXPORT-MY-KEY"
    def runner(command, **kwargs):
        assert secret not in " ".join(command)
        assert kwargs["env"]["PLAYDOCK_SERPER_API_KEY"] == secret
        request = json.loads(Path(command[-2]).read_text(encoding="utf-8"))
        assert request == {"query": "Goblin Nest"}
        assert secret not in str(request)
        Path(command[-1]).write_text(json.dumps({
            "ok": True,
            "rows": [{"title":"Goblin Nest by BadColor",
                      "href":"https://badcolor.itch.io/goblin-nest"}],
            "providers": [{"provider":"google_serper","state":"relevant"}],
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)
    rows = isolated_web_search("Goblin Nest", runner=runner,
                               serper_api_key=secret)
    assert rows[0]["title"] == "Goblin Nest by BadColor"
    assert rows.providers[0]["provider"] == "google_serper"
    assert secret not in str(rows)
    assert secret not in str(rows.providers)


def test_filename_identity_serper_key_never_in_export(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    from experiments.dlsite_detector.filename_web_search import SearchRows
    secret = "PRIVATE-KEY-NOT-IN-RESULT"
    captured = []
    def fake_search(title, *, serper_api_key=""):
        captured.append((title, serper_api_key))
        return SearchRows([{
            "title": "Goblin Nest by BadColor",
            "href": "https://badcolor.itch.io/goblin-nest",
            "body": "Game",
        }], [{"provider": "google_serper",
              "state": "relevant", "result_count": 1}])
    monkeypatch.setattr(identity, "isolated_web_search", fake_search)
    r = identify_filename("Goblin Nest [v1.36].zip", serper_api_key=secret)
    assert r.status == "web_candidate"
    assert captured == [("Goblin Nest", secret)]
    assert secret not in str(r.to_dict())
    assert r.search_providers[0]["provider"] == "google_serper"


def test_serper_not_called_for_code_with_direct_official_lookup(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    monkeypatch.setattr(identity, "isolated_web_search",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("code lookup must not use Google")))
    r = identify_filename(
        "Moon Valley [RJ09999101].zip",
        dlsite_lookup=lambda code: product(code, "Moon Valley"),
        serper_api_key="TEST-ONLY-KEY",
    )
    assert r.status == "official_match"
    assert "TEST-ONLY-KEY" not in str(r.to_dict())


def test_keyless_ddgs_pins_duckduckgo_backend(monkeypatch):
    import sys
    from types import SimpleNamespace
    from experiments.dlsite_detector.pipeline import fast_web_search
    kwargs_seen = []
    class FakeDDGS:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def text(self, q, **kwargs):
            kwargs_seen.append(kwargs)
            return []
    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    assert fast_web_search("Moon Valley") == []
    assert kwargs_seen[0]["backend"] == "duckduckgo"


def test_weak_article_and_rss_error_keeps_partial_evidence(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Moon Valley - Game Review",
        "href": "https://review.example.org/games/moon-valley",
        "body": "PC game review",
    }])
    def fail(_):
        raise RuntimeError("RSS temporarily down")
    monkeypatch.setattr(w, "bing_rss_search", fail)
    trace = []
    rows = w.search_one_title("Moon Valley", trace)
    assert len(rows) == 1
    assert trace[1]["state"] == "error"
    assert trace[0]["strong_page_count"] == 0


def test_provider_canonical_url_deduplication():
    from experiments.dlsite_detector.filename_web_search import _canonical_url
    assert _canonical_url("https://STUDIO.itch.io/moon-valley/?utm_source=x") == (
        "https://studio.itch.io/moon-valley")


def test_rss_fallback_filters_wrong_chapter(monkeypatch):
    from experiments.dlsite_detector import filename_web_search as w, pipeline
    monkeypatch.setattr(pipeline, "fast_web_search", lambda _: [{
        "title": "Moon Valley Chapter 2 by Author",
        "href": "https://author.itch.io/moon-valley-chapter-2",
        "body": "Game chapter",
    }])
    monkeypatch.setattr(w, "bing_rss_search", lambda _: [{
        "title": "Moon Valley Chapter 1 by Author",
        "href": "https://author.itch.io/moon-valley-chapter-1",
        "body": "Game chapter",
    }])
    trace = []
    rows = w.search_one_title("Moon Valley", trace, chapter_hint="1")
    assert len(rows) == 1 and "chapter-1" in rows[0]["href"]
    assert trace[0]["relevant_count"] == 0


def test_worker_chapter_only_transferred_not_original_filename(tmp_path):
    import json
    import subprocess
    from pathlib import Path
    from experiments.dlsite_detector.filename_web_search import isolated_web_search
    def runner(command, **options):
        query = json.loads(Path(command[-2]).read_text(encoding="utf-8"))
        assert query == {"query": "Moon Valley", "chapter": "1"}
        Path(command[-1]).write_text(
            json.dumps({"ok": True, "rows": [], "providers": []}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)
    assert isolated_web_search(
        "Moon Valley", chapter_hint="1", runner=runner
    ) == []


def test_third_party_title_code_rechecked_but_not_confirmed(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    calls = []
    def lookup(code, **kwargs):
        calls.append(code)
        return product(code, "Moon Valley")
    monkeypatch.setattr(identity, "fetch_product", lookup)
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "title": "Moon Valley RJ09999901 game review",
        "href": "https://reviews.example.org/games/moon-valley",
        "body": "game information",
    }])
    assert calls == ["RJ09999901"]
    assert r.status == "likely"
    assert r.candidates[0].source == "search_official_recheck"
    assert r.web_code_hints[0]["state"] == "official_title_verified"
    assert r.to_dict()["web_code_hints"][0]["origin"] == "third_party_search_result"


def test_third_party_code_mismatch_not_promoted(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    monkeypatch.setattr(
        identity, "fetch_product",
        lambda code, **kwargs: product(code, "Other Game"),
    )
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "title": "Moon Valley RJ09999902 game review",
        "href": "https://reviews.example.org/games/moon-valley",
        "body": "game",
    }])
    assert r.web_code_hints[0]["state"] == "title_mismatch"
    assert r.status == "unidentified"
    assert r.rejected_pages
    assert not r.candidates


def test_snippet_only_code_not_sent_to_catalog(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    monkeypatch.setattr(
        identity, "fetch_product",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("snippet code must not trigger catalog lookup")
        ),
    )
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "title": "Moon Valley game review",
        "href": "https://reviews.example.org/games/moon-valley",
        "body": "game listing RJ09999903",
    }])
    assert not r.web_code_hints
    assert r.status == "web_candidate"


def test_dlc_filename_not_confirmed_as_base_game():
    r = identify_filename(
        "Moon Valley [DLC] [RJ09999904].zip",
        dlsite_lookup=lambda code: product(code, "Moon Valley"),
        web_search=fail_web,
    )
    assert r.extracted.archive_kind == "dlc_candidate"
    assert r.status == "likely"
    assert r.is_unresolved


def test_official_code_on_direct_url_keeps_original_behavior(monkeypatch):
    from experiments.dlsite_detector import filename_only as identity
    monkeypatch.setattr(
        identity, "fetch_product",
        lambda code, **kwargs: product(code, "Moon Valley"),
    )
    r = identify_filename("Moon Valley.zip", web_search=lambda _: [{
        "title": "Moon Valley DLsite Game",
        "href": "https://www.dlsite.com/maniax/work/=/product_id/"
                "RJ09999905.html",
        "body": "Game",
    }])
    assert r.status == "official_match"
    assert r.web_code_hints[0]["origin"] == "official_product_url"

