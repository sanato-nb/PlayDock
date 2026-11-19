"""v0.10 이름·품번 전용 정체 판독 회귀 테스트.

합성 ZIP/모의 검색만 사용. 사용자 파일·개인 검사 JSON을 포함하지 않음.
"""
from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from experiments.dlsite_detector.simple_identity import (
    _queries, analyze_identity, collect_identity_clues,
)
from experiments.dlsite_detector.pipeline import SearchDecision


def make_zip(tmp_path, name: str, members: dict[str, bytes]) -> Path:
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        for member, payload in members.items():
            zf.writestr(member, payload)
    return archive


def test_archive_name_and_code_and_readme_are_only_identity_evidence(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999777] [한국어] [v1.2].zip", {
        "Moon Valley/Game.exe": b"fake",
        "Moon Valley/README.txt": b"Title: Moon Valley\n" + "品番: RJ09999777".encode(),
        "Moon Valley/Assets/hidden.json": b'{"name": "Secret Different Game"}',
    })
    scan = collect_identity_clues(path)
    assert scan.encryption_state == "clear"
    assert scan.scan_state == "ok"
    assert scan.readme_state == "ok"
    items = {(x.kind, x.value, x.source) for x in scan.clues}
    assert ("title", "Moon Valley", "archive_name") in items
    assert ("product_code", "RJ09999777", "archive_name") in items
    assert ("product_code", "RJ09999777", "readme") in items
    assert all("Secret Different Game" not in x.value for x in scan.clues)
    assert all(x.kind in {"title", "product_code"} for x in scan.clues)


def test_name_before_code_but_code_also_always_queried(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999777].zip", {
        "Moon Valley/Moon Valley.exe": b"test",
    })
    scan = collect_identity_clues(path)
    assert _queries(scan, 3)[0][0] == "Moon Valley"
    assert "RJ09999777" in [q for q, _ in _queries(scan, 3)]


def test_confirmed_official_title_and_code_are_catalog_identity_not_file_authenticity(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999777].zip", {
        "Moon Valley/Moon Valley.exe": b"fake",
    })
    seen = []
    def classifier(query):
        seen.append(query)
        if query == "RJ09999777":
            return SearchDecision("confirmed_game", query,
                                  proposed_title="Moon Valley",
                                  dlsite_code="RJ09999777")
        return SearchDecision("lookup_unavailable", query)
    result = analyze_identity(path, classifier=classifier)
    assert result.status == "identified"
    assert result.product_code == "RJ09999777"
    assert seen == ["RJ09999777"]
    assert result.to_dict()["local_file_identity_cryptographically_verified"] is False
    assert result.to_dict()["post_identity_checks"] == "deferred"


def test_title_only_game_with_no_local_product_code_can_be_identified(tmp_path):
    path = make_zip(tmp_path, "Star Clouds.zip", {
        "Star Clouds/Star Clouds.exe": b"fake",
    })
    result = analyze_identity(
        path,
        classifier=lambda query: SearchDecision(
            "confirmed_game", query,
            proposed_title="Star Clouds", dlsite_code="RJ09999776",
        ),
    )
    assert result.status == "identified"
    assert result.product_code == "RJ09999776"
    assert all(c.kind != "product_code" for c in result.scan.clues)


def test_multiple_distinct_exes_are_not_promoted_to_search_queries(tmp_path):
    path = make_zip(tmp_path, "Collection.zip", {
        "Collection/Alpha Story.exe": b"fake",
        "Collection/Beta Story.exe": b"fake",
        "Collection/CrashReportClient.exe": b"fake",
    })
    scan = collect_identity_clues(path)
    assert scan.exe_ambiguous is True
    assert scan.exe_candidates == ("Alpha Story", "Beta Story")
    assert all(c.source != "main_exe" for c in scan.clues)
    assert not any("Alpha Story" == q or "Beta Story" == q
                   for q, _ in _queries(scan, 6))


def test_game_exe_and_helpers_choose_unique_main_exe(tmp_path):
    path = make_zip(tmp_path, "Mystery.zip", {
        "Night Sky.exe": b"fake",
        "Night Sky_Data/globalgamemanagers": b"metadata",
        "python.exe": b"fake",
        "tools/createdump.exe": b"fake",
        "Engine/Binaries/Win64/CrashReportClient.exe": b"fake",
        "Uninstaller.exe": b"fake",
    })
    scan = collect_identity_clues(path)
    assert scan.exe_candidates == ("Night Sky",)
    assert any(c.source == "main_exe" and c.value == "Night Sky"
               for c in scan.clues)
    assert all(not any(word in c.value.lower()
                       for word in ("python", "createdump", "crashreportclient"))
               for c in scan.clues)


def test_conflicting_product_codes_are_multiple_candidates(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999775].zip", {
        "Moon Valley/README.txt": b"Title: Moon Valley\n" + b"DLsite Code: RJ09999774\n",
    })
    def classifier(q):
        if q in {"RJ09999775", "RJ09999774"}:
            return SearchDecision("confirmed_game", q, proposed_title="Moon Valley",
                                  dlsite_code=q)
        return SearchDecision("lookup_unavailable", q)
    result = analyze_identity(path, classifier=classifier)
    assert result.status == "multiple"
    assert result.product_code == ""
    assert len(result.alternatives) == 2
    assert result.is_unresolved


def test_official_product_title_mismatch_is_not_confirmed_identity(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999773].zip", {})
    def classifier(q):
        if q == "RJ09999773":
            return SearchDecision("confirmed_game", q,
                                  proposed_title="Another Unrelated Game",
                                  dlsite_code="RJ09999773")
        return SearchDecision("lookup_unavailable", q)
    result = analyze_identity(path, classifier=classifier)
    assert result.status == "likely"
    assert result.is_unresolved


def test_weak_web_candidates_not_promoted_to_official(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {"Moon Valley.exe": b"x"})
    result = analyze_identity(path, classifier=lambda q: SearchDecision(
        "internet_candidate", q, proposed_title="Moon Valley",
        source_platform="itch.io",
    ))
    assert result.status == "likely"
    assert result.product_code == ""
    assert result.is_unresolved


def test_online_network_error_is_not_misclassified_as_nonexistent(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {"Moon Valley.exe": b"x"})
    def failed(q):
        raise RuntimeError("network issue")
    result = analyze_identity(path, classifier=failed)
    assert result.status == "search_error"
    assert result.is_unresolved
    assert result.attempts[0].decision.search_state == "network_error"


def test_unreadable_file_is_unresolved_with_no_network_query(tmp_path):
    path = tmp_path / "not_an_archive.zip"
    path.write_bytes(b"not a zip archive")
    seen = []
    result = analyze_identity(
        path,
        classifier=lambda q: seen.append(q) or SearchDecision(
            "lookup_unavailable", q
        ),
    )
    assert result.scan.scan_state in {"filename_only", "unavailable"}
    assert result.is_unresolved


def test_encrypted_member_never_read_and_only_archive_name_sent(tmp_path, monkeypatch):
    path = make_zip(tmp_path, "Protected Story [RJ09999772].zip", {
        "Hidden Other Game/Hidden Other Game.exe": b"PRIVATE",
        "Hidden Other Game/README.txt": b"Title: Hidden Other Game",
    })
    from experiments.dlsite_detector.archive_encryption import EncryptionProbe
    from experiments.dlsite_detector import simple_identity as mod
    monkeypatch.setattr(mod, "probe_archive_encryption",
                        lambda _: EncryptionProbe("encrypted", "test"))
    def forbidden(*_a, **_k):
        raise AssertionError("Encrypted header should not be listed")
    monkeypatch.setattr(mod, "_list_archive", forbidden)
    scan = collect_identity_clues(path)
    assert scan.readme_state == "not_inspected"
    assert all(c.source == "archive_name" for c in scan.clues)
    result = analyze_identity(path, classifier=lambda q: SearchDecision(
        "confirmed_game", q, proposed_title="Protected Story",
        dlsite_code="RJ09999772",
    ))
    assert result.status == "likely"
    assert "Hidden Other Game" not in " ".join(result.search_queries)


def test_no_exe_content_is_read_only_readme(tmp_path, monkeypatch):
    path = make_zip(tmp_path, "Moon Valley.zip", {
        "Moon Valley.exe": b"SECRET",
        "README.txt": b"Game Title: Moon Valley\n",
    })
    original = zipfile.ZipFile.open
    def only_readme(self, name, *args, **kwargs):
        if isinstance(name, zipfile.ZipInfo):
            path_name = name.filename
        else:
            path_name = str(name)
        assert path_name.casefold().endswith("readme.txt"), path_name
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "open", only_readme)
    scan = collect_identity_clues(path)
    assert any(c.source == "readme" for c in scan.clues)


def test_offline_never_calls_web(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {"Moon Valley.exe": b"x"})
    result = analyze_identity(path, online=False, classifier=lambda _: pytest.fail(
        "web search used while offline"
    ))
    assert result.status == "unidentified"
    assert not result.attempts
    assert result.scan.clues


def test_zip_internal_relative_path_is_never_sent_to_web(tmp_path):
    path = make_zip(tmp_path, "Hidden Moon.zip", {
        "../../private/Secret.exe": b"x",
        "Game/BepInEx/unknown.exe": b"x",
        "Game/Game.exe": b"x",
    })
    queries = []
    result = analyze_identity(path, classifier=lambda q: (
        queries.append(q) or SearchDecision("lookup_unavailable", q)
    ))
    assert not any("/" in q or "\\" in q for q in queries)
    assert all("Secret" not in q for q in queries)
    assert result.scan.clues


def test_script_offline_self_test_importable():
    from scripts.simple_identity_tester import self_test
    assert self_test() == 0



def test_conflicting_readme_and_archive_titles_are_not_officially_identified(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999770].zip", {
        "Moon Valley/README.txt": b"Title: Totally Different Planet\n",
    })
    result = analyze_identity(path, classifier=lambda q: (
        SearchDecision("confirmed_game", q, proposed_title="Moon Valley",
                       dlsite_code="RJ09999770")
        if q == "RJ09999770" else SearchDecision("lookup_unavailable", q)
    ))
    assert result.status == "likely"
    assert any("서로 다른" in n for n in result.notes)


def test_fast_search_includes_conflicting_codes_from_readme(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999769].zip", {
        "Moon Valley/README.txt": b"Title: Moon Valley\nProduct ID: RJ09999768\n",
    })
    scan = collect_identity_clues(path)
    assert [q for q, _ in _queries(scan, 3)] == [
        "Moon Valley", "RJ09999769", "RJ09999768",
    ]



def test_name_only_with_no_secondary_local_evidence_remains_likely(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {
        "data/unknown.bin": b"contents",
    })
    result = analyze_identity(path, classifier=lambda q: SearchDecision(
        "confirmed_game", q, proposed_title="Moon Valley",
        dlsite_code="RJ09999766",
    ))
    assert result.status == "likely"
    assert result.is_unresolved


def test_no_local_code_but_archive_and_main_exe_name_agree_can_be_identified(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {
        "Moon Valley.exe": b"fake",
    })
    result = analyze_identity(path, classifier=lambda q: SearchDecision(
        "confirmed_game", q, proposed_title="Moon Valley",
        dlsite_code="RJ09999765",
    ))
    assert result.status == "identified"
    assert result.product_code == "RJ09999765"



def test_only_first_archive_page_folder_names_can_be_search_candidates(tmp_path):
    """압축을 처음 열 때 보이는 첫 화면의 폴더만 사용한다."""
    path = make_zip(tmp_path, "Moon Valley.zip", {
        "audio/bgm/track.ogg": b"x",
        "plugins/codec/deep.dll": b"x",
        "plugins/audio_filter/filter.dll": b"x",
        "img/characters/hero.png": b"x",
        "Resources/animations/hero.dat": b"x",
        "Game Companion/readme.bin": b"x",
        "Another Story/Inner Title/thing.bin": b"x",
        "Moon Valley.exe": b"MZ",
    })
    scan = collect_identity_clues(path)
    folders = [(c.value, c.detail) for c in scan.clues
               if c.source == "root_folder"]
    assert ("Game Companion", "Game Companion") in folders
    assert ("Another Story", "Another Story") in folders
    assert all("/" not in detail and "\\" not in detail for _, detail in folders)
    bad = {"codec", "audio filter", "bgm", "characters", "animations",
           "Inner Title", "audio", "plugins", "img", "Resources"}
    assert not bad.intersection(c.value for c in scan.clues)
    assert not bad.intersection(q for q, _ in _queries(scan, 6))


def test_first_page_all_generic_folders_produces_only_archive_name_query(tmp_path):
    """실제 스크린샷처럼 audio/css/data/... 가 첫 화면에 있어도 검색하지 않는다."""
    path = make_zip(tmp_path, "Summer Nights.zip", {
        "audio/bgm/track.ogg": b"x",
        "css/style.css": b"x",
        "data/System.json": b"x",
        "effects/Model/m.bin": b"x",
        "fonts/font.ttf": b"x",
        "icon/icon.png": b"x",
        "img/characters/hero.png": b"x",
        "js/libs/plugin.js": b"x",
        "locales/ko/messages": b"x",
        "save/save01.sav": b"x",
        "swiftshader/libEGL.dll": b"x",
        "www/movies/intro.webm": b"x",
    })
    scan = collect_identity_clues(path)
    assert not any(c.source == "root_folder" for c in scan.clues)
    assert [q for q, _ in _queries(scan, 6)] == ["Summer Nights"]
    assert scan.scan_state == "ok"


def test_nested_game_named_folders_are_never_used_even_if_plausible(tmp_path):
    path = make_zip(tmp_path, "Unknown Release.zip", {
        "assets/Legendary Saga/game.bin": b"x",
        "plugins/Very Special Game/mod.dll": b"x",
        "data/RJ09998888/file.bin": b"x",
    })
    scan = collect_identity_clues(path)
    assert [q for q, _ in _queries(scan, 6)] == ["Unknown Release"]
    assert not any(c.value == "RJ09998888" for c in scan.clues)
    assert not any(c.value in {"Legendary Saga", "Very Special Game"}
                   for c in scan.clues)


def test_single_root_wrapper_can_still_be_used_as_name(tmp_path):
    """최상위 단일 게임 폴더명은 1단계 근거로 유지한다."""
    path = make_zip(tmp_path, "Unknown.zip", {
        "Moon Valley/Moon Valley.exe": b"x",
        "Moon Valley/Moon Valley_Data/data.unity3d": b"x",
        "Moon Valley/data/scene.dat": b"x",
    })
    scan = collect_identity_clues(path)
    assert ("Moon Valley", "root_folder") in {
        (c.value, c.source) for c in scan.clues
    }
    assert all(c.detail == "Moon Valley" for c in scan.clues
               if c.source == "root_folder")



def test_confirmed_code_skips_expensive_title_search(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999666].zip", {
        "Moon Valley/Moon Valley.exe": b"fake",
    })
    calls = []
    def classifier(q):
        calls.append(q)
        if q != "RJ09999666":
            raise AssertionError("품번 확인 후 제목 검색 호출 금지")
        return SearchDecision(
            "confirmed_game", q, proposed_title="Moon Valley",
            dlsite_code="RJ09999666",
        )
    result = analyze_identity(path, classifier=classifier)
    assert result.status == "identified"
    assert result.search_queries == ("RJ09999666",)
    assert calls == ["RJ09999666"]


def test_one_timeout_stops_further_names_for_same_archive(tmp_path):
    path = make_zip(tmp_path, "Moon Valley.zip", {
        "Different Story/file.bin": b"x",
        "Moon Valley.exe": b"x",
    })
    seen = []
    def failed(q):
        seen.append(q)
        return SearchDecision(
            "lookup_unavailable", q,
            search_state="network_error",
        )
    result = analyze_identity(path, classifier=failed)
    assert result.status == "search_error"
    assert seen == ["Moon Valley"]
    assert result.search_queries == ("Moon Valley",)


def test_secondary_folder_and_exe_versions_do_not_trigger_duplicate_searches(tmp_path):
    path = make_zip(tmp_path, "BunnyHero [v0.5.2].zip", {
        "BunnyHero-0.5.2-pc/BunnyHero.exe": b"x",
        "BunnyHero-0.5.2-pc/BunnyHero_Data/data.bin": b"x",
    })
    scan = collect_identity_clues(path)
    assert [q for q, _ in _queries(scan, 6)] == ["BunnyHero"]


def test_english_exe_version_removed_without_losing_series_number(tmp_path):
    path = make_zip(tmp_path, "Agent Feminine [v0.4.7].zip", {
        "agent_feminine_0.4.7.exe": b"x",
    })
    scan = collect_identity_clues(path)
    assert [q for q, _ in _queries(scan, 6)] == ["Agent Feminine"]


def test_code_only_patched_product_is_not_identified_as_base_game(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999665].zip", {
        "Moon Valley/Moon Valley.exe": b"x",
    })
    result = analyze_identity(path, classifier=lambda q: (
        SearchDecision("confirmed_game", q,
                       proposed_title="【AI번역 패치】Moon Valley",
                       dlsite_code="RJ09999665")
    ))
    assert result.status == "likely"
    assert result.is_unresolved
    assert "번역 패치" in result.reason


def test_two_declared_codes_one_unavailable_does_not_identify(tmp_path):
    path = make_zip(tmp_path, "Moon Valley [RJ09999664].zip", {
        "README.txt": b"DLsite Code: RJ09999663\n",
    })
    def classify(q):
        if q == "RJ09999664":
            return SearchDecision("confirmed_game", q,
                                  proposed_title="Moon Valley",
                                  dlsite_code=q)
        return SearchDecision("lookup_unavailable", q,
                              search_state="network_error")
    result = analyze_identity(path, classifier=classify)
    assert result.status == "likely"
    assert result.is_unresolved
    assert result.product_code == "RJ09999664"
