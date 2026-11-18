"""v0.5 회귀 검사: 동일 작품 후보 병합·고품질 검색어·대량 검색 캐시·두 단계 판정.

전부 생성한 가상 테스트 자료 사용. 사용자 128개 실제 파일명은 커밋하지 않음.
"""
from __future__ import annotations

import zipfile

from experiments.dlsite_detector.archive_identity import (
    IdentityAttempt, identify_archive,
)
from experiments.dlsite_detector.catalog_aliases import (
    catalog_titles, explicit_title_keys, group_external_attempts,
)
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector.search_plan import build_search_plan
from experiments.dlsite_detector.search_session import SearchSession


def attempt(title, *, code="", steam="", status="internet_candidate"):
    return IdentityAttempt(
        1, "synthetic", title,
        SearchDecision(
            status, title, proposed_title=title,
            dlsite_code=code,
            source_platform="steam" if steam else "",
            source_id=steam,
        ),
    )


def make_zip(tmp_path, name, files):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as arc:
        for member, contents in files.items():
            arc.writestr(member, contents)
    return path


def test_explicit_bilingual_titles_become_one_catalog_candidate():
    entries = (
        attempt("星空セナ - Star Sena -", code="RJ01000999",
                status="confirmed_game"),
        attempt("Star Sena"),
    )
    groups = group_external_attempts(entries)
    assert len(groups) == 1
    assert catalog_titles(entries) == ("星空セナ - Star Sena -",)


def test_explicit_tilde_subtitle_makes_one_candidate():
    entries = (
        attempt("Halcyon Voyage ~陽だまりの物語~",
                code="RJ01000111", status="confirmed_game"),
        attempt("Halcyon Voyage"),
    )
    assert len(group_external_attempts(entries)) == 1


def test_different_official_product_ids_cannot_be_merged_even_with_same_title():
    entries = (
        attempt("Moonlight Story", code="RJ01000111",
                status="confirmed_game"),
        attempt("Moonlight Story", code="RJ01000222",
                status="confirmed_game"),
    )
    assert len(group_external_attempts(entries)) == 2


def test_unverified_translated_patch_must_not_merge_with_base_title():
    entries = (
        attempt("【AI翻訳パッチ】Moonlight Story",
                code="RJ01000111", status="confirmed_game"),
        attempt("Moonlight Story"),
    )
    assert len(group_external_attempts(entries)) == 2


def test_cross_store_weak_word_overlap_is_not_sufficient():
    entries = (
        attempt("Eliminator Jasmine", code="RJ01000444",
                status="confirmed_game"),
        attempt("Jasmine the Eliminator", steam="45678"),
    )
    assert len(group_external_attempts(entries)) == 2


def test_distinct_sequel_number_cannot_disappear():
    entries = (attempt("Dragon Story 1"), attempt("Dragon Story 2"))
    assert len(group_external_attempts(entries)) == 2


def test_common_runtime_names_are_removed_before_search(tmp_path):
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    archive = make_zip(tmp_path, "Moonlight Story [v1.4].zip", {
        "BepInEx/core/file.dll": b"x",
        "D3D12/fake.dll": b"x",
        "licenses/README": b"x",
        "python/player.exe": b"x",
        "extracted/whatever.dat": b"x",
        "Moonlight Story/Moonlight Story.exe": b"x",
        "Moonlight Story/Moonlight Story_Data/app.info":
            "Studio\nMoonlight Story\n",
    })
    index = inspect_archive(archive)
    plan = build_search_plan(archive.name, index, None, max_queries=3)
    terms = [x.query.casefold() for x in plan]
    assert terms[0] == "moonlight story"
    assert not any(
        term in terms
        for term in ("bepinex", "d3d12", "licenses", "player", "python", "extracted")
    )


def test_versioned_executable_and_unity_data_folder_dedup(tmp_path):
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    archive = make_zip(tmp_path, "Bunny Moon [v0.5.2].zip", {
        "Bunny Moon-0.5.2-pc/Bunny Moon.exe": b"x",
        "Bunny Moon-0.5.2-pc/Bunny Moon_Data/app.info":
            "Example Studio\nBunny Moon\n",
    })
    index = inspect_archive(archive)
    plan = build_search_plan(archive.name, index, None, max_queries=3)
    assert [v.query for v in plan] == ["Bunny Moon"]


def test_codes_beat_common_title_and_keep_real_sequel(tmp_path):
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    archive = make_zip(tmp_path, "Story 2 [RJ01000111].zip", {
        "Story 2/Story 2.exe": b"x",
    })
    plan = build_search_plan(
        archive.name, inspect_archive(archive), None, max_queries=2,
    )
    assert [v.query for v in plan] == ["RJ01000111", "Story 2"]


def test_search_session_cache_across_files_uses_no_second_web_request():
    calls = []
    def classify(query):
        calls.append(query)
        return SearchDecision("confirmed_game", query, "Moonlight Story",
                              dlsite_code="RJ01000111")
    session = SearchSession(classify)
    a = session("RJ01000111")
    b = session("RJ01000111")
    assert a.proposed_title == b.proposed_title
    assert calls == ["RJ01000111"]
    assert session.metrics.requests == 1
    assert session.metrics.cache_hits == 1


def test_search_session_breaker_skips_weak_queries_but_allows_code():
    calls = []
    def classify(q):
        calls.append(q)
        return SearchDecision("lookup_unavailable", q,
                              reason="일반 인터넷 검색 오류: RuntimeError")
    session = SearchSession(classify, max_failures=2)
    session("Unsupported Alpha")
    session("Unsupported Beta")
    skipped = session("Other Story")
    session("RJ01000111")
    assert skipped.web_checked is False
    assert "연속 장애" in skipped.reason
    assert calls == ["Unsupported Alpha", "Unsupported Beta", "RJ01000111"]
    assert session.metrics.avoided_requests == 1
    assert session.metrics.network_errors == 3


def test_search_session_does_not_persist_error_as_good_cache():
    calls = []
    def classify(q):
        calls.append(q)
        if len(calls) == 1:
            return SearchDecision("lookup_unavailable", q,
                                  reason="일반 인터넷 검색 오류: RuntimeError")
        return SearchDecision("internet_candidate", q,
                              proposed_title="Moonlight Story")
    session = SearchSession(classify)
    assert session("Moonlight Story").status == "lookup_unavailable"
    assert session("Moonlight Story").status == "internet_candidate"
    assert session.metrics.cache_hits == 0


def test_catalog_and_local_identity_are_separate(tmp_path):
    archive = make_zip(tmp_path, "Moonlight Story [RJ01000111].zip", {
        "Moonlight Story/Game.exe": b"x",
    })
    def classify(q):
        return (SearchDecision("confirmed_game", q,
                               proposed_title="Moonlight Story",
                               dlsite_code="RJ01000111")
                if q == "RJ01000111" else
                SearchDecision("lookup_unavailable", q))
    report = identify_archive(archive, classifier=classify, allow_metadata=True,
                              max_search_queries=3)
    verification = verify_identity(report)
    output = verification.to_dict()
    assert output["catalog_status"] == "official_game_found"
    assert output["catalog_title"] == "Moonlight Story"
    assert output["catalog_product_ids"] == ["dlsite_code:RJ01000111"]
    assert output["local_identity_status"] == "needs_review"
    assert output["automatic_binding_allowed"] is False


def test_official_patch_catalog_type_is_not_automatically_base_game(tmp_path):
    archive = make_zip(tmp_path, "Moonlight Story [RJ01000111].zip", {
        "Moonlight Story/Moonlight Story.exe": b"x",
    })
    report = identify_archive(
        archive,
        classifier=lambda q: SearchDecision(
            "confirmed_game", q,
            proposed_title="【AI翻訳パッチ】Moonlight Story",
            dlsite_code="RJ01000111",
        ) if q == "RJ01000111" else SearchDecision("lookup_unavailable", q),
        allow_metadata=True,
    )
    out = verify_identity(report).to_dict()
    assert out["catalog_release_type"] == "translation_patch"
    assert out["local_identity_status"] == "needs_review"
    assert any("번역 패치/DLC" in item for item in out["blockers"])


def test_one_bilingual_catalog_record_survives_full_pipeline(tmp_path):
    archive = make_zip(tmp_path, "Star Sena [RJ01000999].zip", {
        "Star Sena/Star Sena.exe": b"x",
        "Star Sena/Star Sena_Data/app.info": "Studio\nStar Sena\n",
    })
    def classify(q):
        if q == "RJ01000999":
            return SearchDecision("confirmed_game", q,
                                  proposed_title="星空セナ - Star Sena -",
                                  dlsite_code="RJ01000999")
        return SearchDecision("internet_candidate", q,
                              proposed_title="Star Sena")
    result = identify_archive(archive, classifier=classify, allow_metadata=True,
                              max_search_queries=3)
    assert result.status == "candidate_found"
    ver = verify_identity(result)
    assert ver.catalog_status == "official_game_found"
    assert len(ver.candidate_titles) == 1
    assert ver.verdict != "conflict"
