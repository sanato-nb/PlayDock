"""6단계: 잘못된 게임을 확정하지 않는 규칙 기반 교차검증 테스트.

외부 검색은 모의 SearchDecision으로만 주입한다. 파일/네트워크/DB 변경 없음.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from experiments.dlsite_detector.archive_identity import (
    IdentityAttempt, IdentityReport, identify_archive,
)
from experiments.dlsite_detector.archive_inspector import ArchiveInspection
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.internal_metadata import (
    MetadataEvidence, MetadataInspection,
)
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector import identify_cli


def fixture_report(
    *,
    filename="Unknown.zip", title="Night of Revenge",
    external_status="platform_confirmed_game", steam_id="1621540",
    dlsite_code="", metadata_title="Night of Revenge", metadata_steam="1621540",
    metadata_dlsite="", package=True, extra_titles=(), archive_kind=None,
    index_state="ok", metadata_state="ok", encrypted=False,
):
    external = SearchDecision(
        external_status, filename, proposed_title=title,
        dlsite_code=dlsite_code,
        source_platform="steam" if steam_id else "dlsite",
        source_id=steam_id,
    )
    attempts = (IdentityAttempt(1, "archive_filename", filename, external),)
    signals = ("Windows 실행파일 존재", "Ren'Py 게임 데이터 파일 존재") if package else ()
    inspection = ArchiveInspection(
        filename, "zip", index_state, 5, 5, 12345, False,
        ("Ren'Py",) if package else (), (), (), (), "",
        signals, (),
    )
    evidence = []
    titles = []
    if metadata_title:
        evidence.append(MetadataEvidence(
            "Root/Game.ini", "Title", metadata_title, "title", "strong", "game_ini"
        ))
        titles.append(metadata_title)
    if metadata_steam:
        evidence.append(MetadataEvidence(
            "Root/steam_appid.txt", "steam_appid", metadata_steam,
            "steam_app_id", "strong", "steam_appid_file",
        ))
    if metadata_dlsite:
        evidence.append(MetadataEvidence(
            "Root/Game.ini", "dlsite_code", metadata_dlsite,
            "product_code", "strong", "game_ini",
        ))
    for idx, other in enumerate(extra_titles):
        evidence.append(MetadataEvidence(
            f"Game{idx+1}/Game.ini", "Title", other,
            "title", "strong", "game_ini",
        ))
        titles.append(other)
    metadata = MetadataInspection(
        filename, metadata_state, 2, 64, tuple(titles),
        (metadata_dlsite,) if metadata_dlsite else (), tuple(evidence), "",
        (metadata_steam,) if metadata_steam else (),
    )
    return IdentityReport(
        filename, "candidate_found", 1, title, dlsite_code, "",
        inspection, attempts, metadata,
        "encrypted" if encrypted else "clear",
        (1, 2, 3) if encrypted else (1, 2, 3, 4, 5),
    )


def test_matching_official_steam_id_strong_title_and_game_payload():
    report = fixture_report()
    verified = verify_identity(report)
    assert verified.verdict == "matched"
    assert verified.proposed_title == "Night of Revenge"
    assert verified.comparison[0].id_matches == ("steam_app_id:1621540",)
    assert verified.comparison[0].strong_title_matches == ("Night of Revenge",)
    assert verified.package_assessment == "game_payload_candidate"
    assert verified.automatic_binding_allowed is False
    assert verified.requires_manual_review


def test_official_dlsite_code_correlates_only_with_dlsite_id():
    report = fixture_report(external_status="confirmed_game", steam_id="",
                            dlsite_code="RJ405582", metadata_dlsite="RJ405582",
                            metadata_steam="")
    result = verify_identity(report)
    assert result.verdict == "matched"
    assert result.comparison[0].id_matches == ("dlsite_code:RJ405582",)


def test_same_platform_steam_id_mismatch_is_hard_conflict():
    report = fixture_report(metadata_steam="999999")
    result = verify_identity(report)
    assert result.verdict == "conflict"
    assert "same_platform_official_id_conflict" in result.matched_rules
    assert any("steam_app_id" in s for s in result.blockers)
    assert result.automatic_binding_allowed is False


def test_same_platform_dlsite_mismatch_is_hard_conflict():
    report = fixture_report(external_status="confirmed_game", steam_id="",
                            dlsite_code="RJ405582", metadata_dlsite="RJ405583",
                            metadata_steam="")
    result = verify_identity(report)
    assert result.verdict == "conflict"


def test_steam_and_dlsite_numbers_are_not_compared_as_same_platform():
    report = fixture_report(metadata_steam="", metadata_dlsite="RJ405582")
    result = verify_identity(report)
    assert result.verdict == "likely_candidate"
    assert result.comparison[0].id_conflicts == ()


def test_same_name_and_game_payload_without_independent_id_is_likely():
    report = fixture_report(metadata_steam="")
    result = verify_identity(report)
    assert result.verdict == "likely_candidate"
    assert result.automatic_binding_allowed is False


def test_same_name_only_no_game_payload_is_review():
    report = fixture_report(metadata_steam="", package=False)
    result = verify_identity(report)
    assert result.verdict == "needs_review"


def test_matching_internal_steam_id_but_no_game_payload_is_review():
    report = fixture_report(package=False)
    assert verify_identity(report).verdict == "needs_review"


def test_readme_supporting_title_does_not_raise_confirmation():
    report = fixture_report(metadata_title="", metadata_steam="")
    weak = MetadataEvidence(
        "Root/readme.txt", "Title", "Night of Revenge",
        "title", "supporting", "readme",
    )
    from dataclasses import replace
    report = replace(report, metadata=replace(
        report.metadata, title_candidates=("Night of Revenge",), evidence=(weak,)
    ))
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert not result.comparison[0].strong_title_matches


def test_weak_filename_id_is_not_independent_id_confirmation():
    report = fixture_report(filename="Night of Revenge [Steam 1621540].zip",
                            metadata_steam="")
    result = verify_identity(report)
    assert result.verdict == "likely_candidate"
    assert not result.comparison[0].id_matches
    assert any(e.origin == "filename" for e in result.evidence)


def test_verified_alias_enables_strong_match_without_guessing():
    report = fixture_report(title="달빛 이야기", metadata_title="Moonlight Story")
    original = verify_identity(report)
    assert original.verdict == "needs_review"
    corrected = verify_identity(
        report, verified_aliases={"달빛 이야기": ["Moonlight Story"]}
    )
    assert corrected.verdict == "matched"
    assert corrected.comparison[0].verified_alias_matches == ("Moonlight Story",)


def test_no_unverified_fuzzy_match_for_sequel():
    report = fixture_report(title="Adventure", metadata_title="Adventure II")
    assert verify_identity(report).verdict == "needs_review"


def test_different_internal_roots_block_matched_even_with_same_id():
    from dataclasses import replace
    report = fixture_report()
    changed = []
    for item in report.metadata.evidence:
        if item.kind == "steam_app_id":
            changed.append(replace(item, member="DifferentGame/steam_appid.txt"))
        else:
            changed.append(item)
    report = replace(report, metadata=replace(report.metadata, evidence=tuple(changed)))
    result = verify_identity(report)
    assert result.verdict == "likely_candidate"
    assert result.automatic_binding_allowed is False


@pytest.mark.parametrize("name", (
    "Night of Revenge [패치 전용].zip",
    "Night of Revenge [DLC].zip",
    "Night of Revenge [Server].zip",
    "Night of Revenge + Another Game.zip",
))
def test_non_base_distribution_never_confirms_single_game(name):
    report = fixture_report(filename=name)
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert result.package_assessment in {
        "patch_candidate", "dlc_candidate", "server_package_candidate", "bundle_candidate",
    }


def test_localized_filename_does_not_mean_patch_only():
    report = fixture_report(filename="Night of Revenge [한글패치].zip")
    result = verify_identity(report)
    assert result.archive_kind == "localized_release_unknown"
    assert result.package_assessment == "game_payload_candidate"
    assert result.verdict == "matched"
    assert result.localization_assessment == "not_verified"


def test_korean_translation_files_alone_are_not_proof_of_functioning_translation():
    from dataclasses import replace
    report = fixture_report()
    report = replace(report, inspection=replace(
        report.inspection,
        localization_signals=("한국어 번역 파일/폴더 경로 단서",),
    ))
    result = verify_identity(report)
    assert result.localization_assessment == "korean_files_present_unverified"
    assert result.verdict == "matched"


def test_encrypted_archive_ignores_even_injected_internal_evidence():
    report = fixture_report(filename="Night of Revenge [한글패치].zip", encrypted=True)
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert result.inspection_state == "ok"  # 감지 상태는 참고용, 근거는 사용 금지
    assert all(e.origin not in {"internal_index", "internal_metadata"}
               for e in result.evidence)
    assert result.package_assessment == "unverified"
    assert result.automatic_binding_allowed is False


def test_encrypted_no_filename_search_is_unclassifiable():
    from dataclasses import replace
    report = fixture_report(encrypted=True)
    report = replace(report, attempts=(IdentityAttempt(
        1, "archive_filename", report.archive_name,
        SearchDecision("lookup_unavailable", report.archive_name),
    ),), proposed_title="")
    result = verify_identity(report)
    assert result.verdict == "unclassifiable"
    assert result.candidate_titles == ()


def test_unknown_encryption_only_uses_external_title():
    from dataclasses import replace
    report = replace(fixture_report(), encryption_state="unknown")
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert result.package_assessment == "unverified"


def test_multiple_external_game_candidates_not_auto_collapsed():
    from dataclasses import replace
    report = fixture_report()
    attempt2 = IdentityAttempt(
        2, "internal_filename", "Another Game",
        SearchDecision("internet_candidate", "Another Game", proposed_title="Another Game"),
    )
    report = replace(report, attempts=report.attempts + (attempt2,))
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert len(result.candidate_titles) == 2
    assert result.proposed_title == ""


def test_only_trusted_explicit_alias_map_merges_two_external_titles():
    from dataclasses import replace
    report = fixture_report()
    attempt2 = IdentityAttempt(
        2, "internal_filename", "복수 원제",
        SearchDecision("internet_candidate", "복수 원제", proposed_title="복수 원제"),
    )
    report = replace(report, attempts=report.attempts + (attempt2,))
    without = verify_identity(report)
    assert without.verdict == "needs_review"
    merged = verify_identity(report, verified_aliases={
        "Night of Revenge": ["복수 원제"]
    })
    assert len(merged.candidate_titles) == 1
    assert merged.verdict == "matched"


def test_multiple_strong_internal_game_titles_are_review_not_single_game():
    report = fixture_report(extra_titles=("Another Game",))
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert "possible_multiple_games_or_aliases" in result.matched_rules


def test_explicit_bundle_with_two_titles_is_review():
    report = fixture_report(filename="Night of Revenge + Another.zip",
                            extra_titles=("Another Game",))
    result = verify_identity(report)
    assert result.verdict == "needs_review"
    assert "bundle_multiple_titles" in result.matched_rules


def test_only_internal_metadata_title_does_not_become_likely_without_external_lookup():
    from dataclasses import replace
    report = fixture_report()
    report = replace(report, attempts=(IdentityAttempt(
        1, "archive_filename", "Unknown",
        SearchDecision("lookup_unavailable", "Unknown"),
    ),), proposed_title="")
    outcome = verify_identity(report)
    assert outcome.verdict == "needs_review"
    assert outcome.candidate_titles == ("Night of Revenge",)
    assert outcome.automatic_binding_allowed is False


def test_no_usable_external_or_internal_evidence_is_unclassifiable():
    from dataclasses import replace
    report = fixture_report(metadata_steam="", metadata_title="", package=False)
    report = replace(report, attempts=(IdentityAttempt(
        1, "archive_filename", "Unknown",
        SearchDecision("lookup_unavailable", "Unknown"),
    ),), proposed_title="")
    result = verify_identity(report)
    assert result.verdict == "unclassifiable"


@pytest.mark.parametrize("state", ("partial", "limit_exceeded", "unavailable"))
def test_incomplete_archive_index_cannot_confirm(state):
    report = fixture_report(index_state=state)
    assert verify_identity(report).verdict != "matched"


def test_metadata_unavailable_cannot_confirm_even_with_title_from_old_result():
    report = fixture_report(metadata_state="index_only")
    result = verify_identity(report)
    assert result.verdict != "matched"


def test_read_only_report_contains_reasons_provenance_and_separate_category():
    result = verify_identity(fixture_report())
    item = result.to_dict()
    assert item["verdict"] == "matched"
    assert item["archive_kind"] == "unknown"
    assert item["comparison"][0]["official"] is True
    assert item["evidence"]
    assert item["matched_rules"]
    assert item["limitations"]
    assert item["read_only"] is True
    assert item["automatic_binding_allowed"] is False
    assert item["requires_manual_review"] is True


def test_real_zip_integration_and_no_mutation(tmp_path):
    archive = tmp_path / "Night of Revenge [한글패치].zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Root/Game.ini", "Title=Night of Revenge\n")
        z.writestr("Root/steam_appid.txt", "1621540\n")
        z.writestr("Root/Root.exe", b"FAKE EXE")
        z.writestr("Root/game/archive.rpa", b"FAKE GAME DATA")
        z.writestr("Root/game/tl/korean/script.rpy", b"translation")
    original = archive.read_bytes()
    def official(query):
        return SearchDecision("platform_confirmed_game", query,
                              proposed_title="Night of Revenge",
                              source_platform="steam", source_id="1621540")
    report = identify_archive(archive, classifier=official, allow_metadata=True)
    result = verify_identity(report)
    assert report.completed_steps == (1, 2, 3, 4, 5)
    assert result.verdict == "matched"
    assert result.localization_assessment == "korean_files_present_unverified"
    assert archive.read_bytes() == original


def test_cli_verify_returns_nested_read_only_json(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "Unknown.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Root/Game.ini", "Title=Night of Revenge\n")
        z.writestr("Root/steam_appid.txt", "1621540\n")
        z.writestr("Root/Main.exe", b"EXE")
        z.writestr("Root/game/archive.rpa", b"RPA")
    def fake_identify(path, **kwargs):
        return identify_archive(
            path, classifier=lambda q: SearchDecision(
                "platform_confirmed_game", q, proposed_title="Night of Revenge",
                source_platform="steam", source_id="1621540",
            ), **kwargs)
    monkeypatch.setattr(identify_cli, "identify_archive", fake_identify)
    exit_code = identify_cli.main([str(archive), "--online", "--verify", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["stages_1_to_5"]["completed_steps"] == [1, 2, 3, 4, 5]
    assert data["verification"]["verdict"] == "matched"
    assert data["verification"]["automatic_binding_allowed"] is False


def test_cli_verify_rejects_offline_mode(tmp_path):
    archive = tmp_path / "Unknown.zip"
    archive.write_bytes(b"invalid")
    with pytest.raises(SystemExit) as error:
        identify_cli.main([str(archive), "--verify"])
    assert error.value.code == 2


def test_two_official_steam_products_cannot_merge_even_with_verified_alias():
    from dataclasses import replace
    report = fixture_report()
    second = IdentityAttempt(
        2, "internal_filename", "Alias Game",
        SearchDecision(
            "platform_confirmed_game", "Alias Game",
            proposed_title="Alias Game", source_platform="steam",
            source_id="999999",
        ),
    )
    report = replace(report, attempts=report.attempts + (second,))
    # Even though the alias mapping is explicit, two distinct official
    # products must not be turned into the same installed game.
    result = verify_identity(report, verified_aliases={
        "Night of Revenge": ["Alias Game"]
    })
    assert result.verdict == "conflict"
    assert "multiple_official_product_ids" in result.matched_rules
    assert result.automatic_binding_allowed is False


def test_distinct_dlsite_codes_from_two_official_matches_block_auto_merge():
    from dataclasses import replace
    report = fixture_report(external_status="confirmed_game", steam_id="",
                            dlsite_code="RJ405582", metadata_steam="",
                            metadata_dlsite="RJ405582")
    second = IdentityAttempt(
        2, "internal_product_code", "RJ405583",
        SearchDecision(
            "confirmed_game", "RJ405583", proposed_title="Night of Revenge",
            dlsite_code="RJ405583",
        ),
    )
    report = replace(report, attempts=report.attempts + (second,))
    result = verify_identity(report)
    assert result.verdict == "conflict"
    assert "multiple_official_product_ids" in result.matched_rules
