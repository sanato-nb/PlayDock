"""v0.9 정확도 회귀: 실제 판독에서 발견한 오류를 합성 입력으로 재현.

실제 사용자 압축파일 목록/개인 JSON을 공개 코드에 포함하지 않는다.
원본 파일은 오직 ZIP 헤더만 검사하고 게임 프로그램은 실행하지 않는다.
"""
from __future__ import annotations

import zipfile

from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.archive_identity import (
    IdentityAttempt, IdentityReport, identify_archive,
)
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.internal_metadata import inspect_readme_metadata
from experiments.dlsite_detector.pipeline import SearchDecision, examine_web_results
from experiments.dlsite_detector.search_plan import build_search_plan


def make_zip(tmp_path, name, files):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        for member, payload in files.items():
            archive.writestr(member, payload)
    return path


def test_runtime_and_crash_executables_are_not_game_title_searches(tmp_path):
    path = make_zip(tmp_path, "Mystic Valley.zip", {
        "Mystic Valley.exe": b"exe",
        "Mystic Valley_Data/level0": b"unity",
        "lib/python.exe": b"py",
        "lib/pythonw.exe": b"py",
        "lib/zsync.exe": b"updater",
        "tools/createdump.exe": b"dump",
        "Engine/Binaries/Win64/CrashReportClient.exe": b"crash",
        "OpenSaveFolder.exe": b"helper",
        "ResetConfig.exe": b"helper",
        "Uninstaller.exe": b"helper",
        "BepInEx/plugins/helper.exe": b"mod",
        "MonoBleedingEdge/runtime.dll": b"x",
    })
    index = inspect_archive(path)
    assert "Mystic Valley" in index.title_candidates
    assert not any(x.casefold() in {"python", "pythonw", "zsync",
                                   "createdump", "crashreportclient",
                                   "opensavefolder", "resetconfig",
                                   "uninstaller", "bepinex",
                                   "monobleedingedge"}
                   for x in index.title_candidates)
    assert any("Unity 데이터 폴더" in e.reason for e in index.evidence)
    plan = build_search_plan(path.name, index, None, max_queries=6)
    assert [x.query for x in plan] == ["Mystic Valley"]


def test_generic_player_and_galleries_are_not_searched(tmp_path):
    path = make_zip(tmp_path, "Episode One.zip", {
        "player.exe": b"player",
        "CG Hero/gallery.png": b"cg",
        "【特典】Free Images/bonus.jpg": b"bonus",
        "extracted/misc.bin": b"junk",
        "manual/README.pdf": b"manual",
        "Episode One/assets.dat": b"data",
    })
    index = inspect_archive(path)
    assert "player" not in index.title_candidates
    assert not any(x.startswith(("CG ", "【特典】", "extracted", "manual"))
                   for x in index.title_candidates)
    queries = [h.query for h in build_search_plan(path.name, index, None)]
    assert queries == ["Episode One"]


def test_unreal_shipping_exe_is_possible_title_but_engine_crash_is_not(tmp_path):
    path = make_zip(tmp_path, "Cosmic Border.zip", {
        "ProjectX.exe": b"launcher",
        "ProjectX/Binaries/Win64/ProjectX-Win64-Shipping.exe": b"game",
        "Engine/Binaries/Win64/CrashReportClient.exe": b"crash",
        "Engine/Binaries/Win64/UnrealCEFSubProcess.exe": b"helper",
    })
    result = inspect_archive(path)
    assert "ProjectX" in result.title_candidates
    assert "CrashReportClient" not in result.title_candidates
    assert "UnrealCEFSubProcess" not in result.title_candidates


def test_web_concatenated_headline_is_retained_but_not_used_as_exact_match():
    bad = "Moon Valley on Steam" + ("Moon Valley - MobyGames" * 10)
    hits = examine_web_results("Moon Valley", [{
        "href": "https://store.steampowered.com/app/1234567/Moon_Valley/",
        "title": bad,
        "body": "game download",
    }])
    assert len(hits) == 1
    assert not hits[0].strong_match
    assert not hits[0].game_context
    assert hits[0].title.startswith("Moon Valley on Steam")


def test_japanese_readme_product_code_field(tmp_path):
    path = make_zip(tmp_path, "Japanese Sky.zip", {
        "Japanese Sky.exe": b"exe",
        "README.txt": "ゲームタイトル: Japanese Sky\n品番: RJ09999883\n".encode("utf-8"),
    })
    basic = inspect_readme_metadata(path)
    assert basic.title_candidates == ("Japanese Sky",)
    assert basic.product_codes == ("RJ09999883",)


def _report(title1, code1, title2, code2):
    attempts = (
        IdentityAttempt(1, "archive_filename_code", code1,
                        SearchDecision("confirmed_game", code1,
                                       proposed_title=title1,
                                       dlsite_code=code1)),
        IdentityAttempt(1, "archive_filename", title2,
                        SearchDecision("confirmed_game", title2,
                                       proposed_title=title2,
                                       dlsite_code=code2)),
    )
    return IdentityReport(
        title2 + ".zip", "ambiguous", 2, "", "", "",
        None, attempts, None, "clear", (1, 3, 2),
    )


def test_translation_patch_and_original_are_related_hypothesis_not_conflict():
    report = _report(
        "【AI翻訳パッチ】Moon Valley", "RJ09999881",
        "Moon Valley", "RJ09999882",
    )
    result = verify_identity(report)
    assert result.catalog_status == "related_products_review"
    assert result.verdict == "needs_review"
    assert result.catalog_release_type == "mixed_related_products"
    assert len(result.candidate_relationships) == 1
    assert all(code in result.candidate_relationships[0]
               for code in ("RJ09999881", "RJ09999882"))
    assert not result.automatic_binding_allowed
    assert len(result.comparison) == 2


def test_unrelated_separate_official_codes_are_still_conflict():
    result = verify_identity(_report(
        "Moon Valley", "RJ09999880",
        "Another Moon Valley", "RJ09999879",
    ))
    assert result.catalog_status == "conflicting_official_ids"
    assert result.verdict == "conflict"
    assert not result.candidate_relationships


def test_official_ids_do_not_leak_between_version_variants():
    result = verify_identity(_report(
        "Cloud Harbor v1.02", "RJ09999878",
        "Cloud Harbor", "RJ09999877",
    ))
    assert len(result.comparison) == 2
    ids = {item.title: item.official_ids for item in result.comparison}
    assert ids["Cloud Harbor v1.02"] == ("dlsite_code:RJ09999878",)
    assert ids["Cloud Harbor"] == ("dlsite_code:RJ09999877",)


def test_index_scan_and_search_never_read_executable_contents(tmp_path, monkeypatch):
    path = make_zip(tmp_path, "Forest Moon.zip", {
        "Forest Moon.exe": b"MZ",
        "Forest Moon_Data/level0": b"not-real-game-data",
        "tools/createdump.exe": b"secret",
    })
    def blocked(*args, **kwargs):
        raise AssertionError("EXE 파일 내용 읽기 금지")
    monkeypatch.setattr(zipfile.ZipFile, "open", blocked)
    seen = []
    def fake_search(q):
        seen.append(q)
        return SearchDecision("lookup_unavailable", q, search_state="not_found")
    identify_archive(path, classifier=fake_search, allow_metadata=True)
    assert seen == ["Forest Moon"]
