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
    assert output["catalog_product_ids"] == ("dlsite_code:RJ01000111",)
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


def test_single_official_store_page_is_web_candidate_only():
    from experiments.dlsite_detector import pipeline

    def no_dlsite(name, *, code="", allow_title_search=False):
        from experiments.dlsite_detector.detector import Detection
        return Detection("unverified", name)

    result = pipeline.classify_game(
        "Moonlight Story",
        dlsite_lookup=no_dlsite,
        web_search=lambda q: [{
            "title": "Moonlight Story - itch.io",
            "href": "https://fable-studio.itch.io/moonlight-story",
            "body": "An indie game",
        }],
        max_variants=1,
        allow_single_store_candidate=True,
    )
    assert result.status == "internet_candidate"
    assert result.proposed_title == "Moonlight Story"
    assert result.source_platform == "itch.io"
    assert not result.dlsite_code


def test_itch_developer_profile_is_not_assumed_to_be_a_game():
    from experiments.dlsite_detector import pipeline
    from experiments.dlsite_detector.detector import Detection

    result = pipeline.classify_game(
        "Moonlight Studio", dlsite_lookup=lambda *a, **kw:
        Detection("unverified", "Moonlight Studio"),
        web_search=lambda q: [{
            "title": "Moonlight Studio - itch.io",
            "href": "https://moonlight-studio.itch.io/",
            "body": "Games by Moonlight Studio",
        }],
        max_variants=1, allow_single_store_candidate=True,
    )
    assert result.status == "lookup_unavailable"


def test_itch_official_devlog_and_possessive_title_are_only_web_candidate():
    from experiments.dlsite_detector import pipeline
    from experiments.dlsite_detector.detector import Detection

    result = pipeline.classify_game(
        "elenastory", dlsite_lookup=lambda *a, **kw:
        Detection("unverified", "elenastory"),
        web_search=lambda q: [{
            "title": "Update 1.5 is Now Live! - Elena's Story by Example Studio",
            "href": "https://example-studio.itch.io/elenas-story/devlog/5555/update-15",
            "body": "Game update",
        }],
        max_variants=1, allow_single_store_candidate=True,
    )
    assert result.status == "internet_candidate"
    assert result.proposed_title == "Elena's Story"
    assert result.source_platform == "itch.io"


def test_unrelated_store_game_is_not_linked_by_developer_name():
    from experiments.dlsite_detector import pipeline
    from experiments.dlsite_detector.detector import Detection

    result = pipeline.classify_game(
        "BunnyHero", dlsite_lookup=lambda *a, **kw:
        Detection("unverified", "BunnyHero"),
        web_search=lambda q: [{
            "title": "The Selfish Bunny by BunnyHero - itch.io",
            "href": "https://bunnyhero.itch.io/the-selfish-bunny",
            "body": "A game made by BunnyHero",
        }],
        max_variants=1, allow_single_store_candidate=True,
    )
    assert result.status == "lookup_unavailable"


def test_circuit_breaker_eventually_probes_to_recover(monkeypatch):
    from experiments.dlsite_detector import search_session
    clock = {"now": 100.0}
    monkeypatch.setattr(search_session.time, "monotonic", lambda: clock["now"])
    calls = []

    def unstable(q):
        calls.append(q)
        if len(calls) <= 2:
            return SearchDecision("lookup_unavailable", q,
                                  reason="일반 인터넷 검색 오류: RuntimeError")
        return SearchDecision("internet_candidate", q, proposed_title=q)

    session = SearchSession(unstable, max_failures=2, cooldown_seconds=20)
    assert session("Story One").status == "lookup_unavailable"
    assert session("Story Two").status == "lookup_unavailable"
    assert session("Story Three").web_checked is False
    clock["now"] = 121.0
    assert session("Story Four").status == "internet_candidate"
    assert session("Story Five").status == "internet_candidate"
    assert calls == ["Story One", "Story Two", "Story Four", "Story Five"]
    assert session.metrics.avoided_requests == 1


def test_web_code_in_third_party_title_is_retained_without_official_claim():
    from experiments.dlsite_detector.enhanced_search import enhanced_classify_game
    from experiments.dlsite_detector.detector import Detection
    from experiments.dlsite_detector.pipeline import classify_game

    def no_dlsite(title, **kwargs):
        return Detection("unverified", title)

    original = classify_game(
        "별하늘 여행", dlsite_lookup=no_dlsite,
        web_search=lambda q: [{
            "title": "별하늘 여행 RJ09999999 - 커뮤니티 정보",
            "href": "https://third-party.example/games/rj09999999",
            "body": "정보",
        }], max_variants=1,
    )
    assert original.status == "lookup_unavailable"
    result = enhanced_classify_game(
        "별하늘 여행", classifier=lambda *args, **kwargs: original,
        web_recovery_lookup=lambda *args, **kwargs:
            Detection("unverified", "RJ09999999"),
        steam_fetcher=lambda *_: None,
    )
    assert result.status == "internet_candidate"
    assert result.web_code_hints == ("RJ09999999",)
    assert not result.official_code_verified
    assert not result.dlsite_code


def test_web_code_official_relookup_is_still_local_unverified(tmp_path):
    from experiments.dlsite_detector.enhanced_search import enhanced_classify_game
    from experiments.dlsite_detector.detector import Detection
    from experiments.dlsite_detector.pipeline import classify_game
    from dataclasses import replace

    initial = classify_game(
        "가상 은하 산책",
        dlsite_lookup=lambda t, **kw: Detection("unverified", t),
        web_search=lambda q: [{
            "title": "RJ09999998 가상 은하 산책 - 제3자 목록",
            "href": "https://third-party.example/item/RJ09999998",
            "body": "게임 추정",
        }], max_variants=1,
    )
    result = enhanced_classify_game(
        "가상 은하 산책", classifier=lambda *args, **kwargs: initial,
        web_recovery_lookup=lambda title, **kw: Detection(
            "needs_review", title, code=kw["code"],
            work_title="Galaxy Walk Official", work_type="RPG",
        ),
        steam_fetcher=lambda *_: None,
    )
    assert result.status == "internet_candidate"
    assert result.official_code_verified
    assert result.dlsite_code == "RJ09999998"
    archive = make_zip(tmp_path, "가상 은하 산책.zip", {
        "가상 은하 산책/게임.exe": b"x",
    })
    stages = identify_archive(archive, classifier=lambda q: result,
                              allow_metadata=True)
    report = verify_identity(stages)
    assert report.catalog_status == "official_game_found"
    assert report.local_identity_status == "needs_review"
    assert not report.automatic_binding_allowed


def test_network_failure_and_true_empty_search_are_separated():
    from experiments.dlsite_detector.pipeline import classify_game
    from experiments.dlsite_detector.detector import Detection

    no_dlsite = lambda title, **kw: Detection("unverified", title)
    empty = classify_game("Empty Galaxy", dlsite_lookup=no_dlsite,
                          web_search=lambda q: [], max_variants=1)
    assert empty.search_state == "not_found"
    def unavailable(_):
        raise RuntimeError("network down")
    failed = classify_game("Empty Galaxy", dlsite_lookup=no_dlsite,
                           web_search=unavailable, max_variants=1)
    assert failed.search_state == "network_error"


def test_cooldown_deferred_queries_are_retryable_without_reopening_zip(monkeypatch):
    from experiments.dlsite_detector import search_session
    clock = {"now": 10.0}
    monkeypatch.setattr(search_session.time, "monotonic", lambda: clock["now"])
    calls = []
    def intermittent(query):
        calls.append(query)
        if len(calls) <= 2:
            raise RuntimeError("offline")
        return SearchDecision("internet_candidate", query, proposed_title=query)

    session = SearchSession(intermittent, max_failures=2, cooldown_seconds=20)
    session("First Query")
    session("Second Query")
    skipped = session("Third Query")
    assert skipped.search_state == "cooldown_skipped"
    assert set(session.pending_queries) == {"First Query", "Second Query", "Third Query"}
    assert session.retry_pending(max_queries=2) == {}
    clock["now"] = 31.0
    refreshed = session.retry_pending(max_queries=3)
    assert len(refreshed) == 3
    assert not session.pending_queries
    assert len(calls) == 5


def test_same_title_across_unlinked_platforms_does_not_merge():
    entries = (
        attempt("Star Trek", code="RJ09999997", status="confirmed_game"),
        attempt("Star Trek", steam="123456", status="platform_confirmed_game"),
    )
    assert len(group_external_attempts(entries)) == 2


def test_phase_timings_are_nonnegative_and_source_archive_is_unchanged(tmp_path):
    import hashlib
    archive = make_zip(tmp_path, "Phase Clock Game.zip", {
        "Phase Clock Game/Clock.exe": b"not executable",
        "Phase Clock Game/Clock_Data/app.info": "Studio\nPhase Clock Game\n",
    })
    checksum_before = hashlib.sha256(archive.read_bytes()).hexdigest()
    seen = []
    def classify(query):
        seen.append(query)
        return SearchDecision("lookup_unavailable", query, search_state="not_found")
    report = identify_archive(archive, classifier=classify, allow_metadata=True,
                              max_search_queries=2)
    verification = verify_identity(report)
    clocks = report.to_dict()["stage_timings_ms"]
    assert set(("archive_name_parse_ms", "encryption_probe_ms",
                "index_scan_ms", "metadata_read_ms", "search_ms",
                "verification_ms")).issubset(clocks)
    assert all(value >= 0 for value in clocks.values())
    assert report.execution_order.index(4) < report.execution_order.index(2)
    assert report.execution_order.index(5) < report.execution_order.index(2)
    assert seen and not verification.automatic_binding_allowed
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum_before



def test_recheck_only_retries_failed_search_without_reopening_archive(tmp_path):
    from experiments.dlsite_detector.archive_identity import (
        recheck_archive_search, search_recheck_needed,
    )
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    from experiments.dlsite_detector.internal_metadata import inspect_metadata
    path = make_zip(tmp_path, "Recheck Sky.zip", {
        "Recheck Sky/Recheck Sky.exe": b"test",
        "Recheck Sky/Recheck Sky_Data/app.info": "Studio\nRecheck Sky\n",
    })
    seen = {"index": 0, "metadata": 0, "requery": []}
    def indexer(p):
        seen["index"] += 1
        return inspect_archive(p)
    def metareader(p):
        seen["metadata"] += 1
        return inspect_metadata(p)
    before = identify_archive(
        path, classifier=lambda q: SearchDecision(
            "lookup_unavailable", q, search_state="network_error",
            reason="검색 오류: RuntimeError",
        ), inspector=indexer, metadata_reader=metareader,
        allow_metadata=True, max_search_queries=3,
    )
    assert search_recheck_needed(before)
    st = path.stat()
    signature = (st.st_size, st.st_mtime_ns)
    def recovered(query):
        seen["requery"].append(query)
        return SearchDecision(
            "confirmed_game", query, proposed_title="Recheck Sky",
            dlsite_code="RJ09999996",
        )
    after = recheck_archive_search(
        path, before, classifier=recovered, expected_stat=signature,
        max_search_queries=3,
    )
    assert after.local_evidence_reused
    assert seen["index"] == 1 and seen["metadata"] == 1
    assert seen["requery"]
    assert not search_recheck_needed(after)
    assert verify_identity(after).catalog_status == "official_game_found"


def test_recheck_file_changed_disables_cached_index(tmp_path):
    from experiments.dlsite_detector.archive_identity import recheck_archive_search
    path = make_zip(tmp_path, "Change Sky.zip", {"Change Sky.exe": b"a"})
    previous = identify_archive(
        path, classifier=lambda q: SearchDecision("lookup_unavailable", q),
        allow_metadata=False,
    )
    st = path.stat()
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("Another.exe", b"b")
    updated = recheck_archive_search(
        path, previous, expected_stat=(st.st_size, st.st_mtime_ns),
        classifier=lambda q: SearchDecision("lookup_unavailable", q),
    )
    assert not updated.local_evidence_reused
    assert updated.inspection.member_count >= 2



def test_verified_cross_store_link_can_connect_separate_language_titles():
    from experiments.dlsite_detector.archive_identity import IdentityAttempt
    from experiments.dlsite_detector.pipeline import SearchDecision
    a = attempt("星界の航海", code="RJ09999995", status="confirmed_game")
    b = attempt("Voyage of Starlight", steam="123456", status="platform_confirmed_game")
    bridge = IdentityAttempt(
        1, "verified_cross_platform_link", "RJ09999995",
        SearchDecision(
            "confirmed_game", "RJ09999995",
            proposed_title="星界の航海 - Voyage of Starlight",
            dlsite_code="RJ09999995", source_platform="dlsite+steam",
            source_id="123456",
        ),
    )
    assert len(group_external_attempts((a, b))) == 2
    assert len(group_external_attempts((a, b, bridge))) == 1
    assert len(group_external_attempts((bridge, a, b))) == 1


def test_cross_store_bridge_cannot_erase_a_different_official_code():
    from experiments.dlsite_detector.archive_identity import IdentityAttempt
    from experiments.dlsite_detector.pipeline import SearchDecision
    a = attempt("Star Ocean One", code="RJ09999994", status="confirmed_game")
    b = attempt("Star Ocean One", code="RJ09999993", status="confirmed_game")
    c = IdentityAttempt(
        1, "verified_cross_platform_link", "RJ09999994",
        SearchDecision(
            "confirmed_game", "RJ09999994",
            proposed_title="Star Ocean One",
            dlsite_code="RJ09999994", source_platform="dlsite+steam",
            source_id="234567",
        ),
    )
    assert len(group_external_attempts((a, b, c))) == 2



def test_official_relookup_network_error_is_retryable_and_not_cached():
    from experiments.dlsite_detector.enhanced_search import enhanced_classify_game
    from experiments.dlsite_detector.pipeline import WebEvidence
    from experiments.dlsite_detector.detector import Detection
    calls = []
    original = SearchDecision(
        "lookup_unavailable", "Fiction Galaxy",
        evidence=(WebEvidence(
            "Fiction Galaxy RJ09999992", "https://example.org/g/RJ09999992",
            "example.org", False, True, False,
        ),),
        search_state="unverified_evidence",
    )
    def unavailable(title, **kw):
        calls.append(kw["code"])
        return Detection("lookup_unavailable", title, reason="HTTP 503")
    def classify(q):
        return enhanced_classify_game(
            q, classifier=lambda *a, **kw: original,
            web_recovery_lookup=unavailable,
            steam_fetcher=lambda *_: None,
        )
    session = SearchSession(classify, max_failures=2)
    a = session("Fiction Galaxy")
    b = session("Fiction Galaxy")
    assert a.status == "internet_candidate"
    assert a.search_state == "network_error"
    assert a.web_code_hints == ("RJ09999992",)
    assert a.dlsite_code == ""
    assert b.search_state == "network_error"
    assert calls == ["RJ09999992", "RJ09999992"]
    assert session.metrics.cache_hits == 0
    assert session.metrics.network_errors == 2



def test_v07_index_only_and_readme_limited_source_content(tmp_path, monkeypatch):
    """공식 번호가 없더라도 압축파일명+내부 파일명 수집 뒤에만 검색."""
    import zipfile
    from experiments.dlsite_detector import internal_metadata as m
    archive = make_zip(tmp_path, "Silver Lantern.zip", {
        "Internal-Project/Star Runner.exe": b"MZ",
        "Internal-Project/Star Runner_Data/app.info": b"Studio\\nHidden Private Title\\n",
        "Internal-Project/game.ini": b"Title=Hidden Ini Title\\n",
        "Internal-Project/System.json": b'{"gameTitle": "Hidden System Title"}',
        "Internal-Project/package.json": b'{"window":{"title":"Hidden Package"}}',
        "Internal-Project/README.txt":
            b"Game Title: Silver Lantern\\nNotes: internal token SECRET123\\n",
    })
    opened = []
    real_open = zipfile.ZipFile.open
    def spy_open(self, name, *a, **kw):
        member = str(name)
        opened.append(member)
        assert member.lower().endswith("readme.txt"), member
        return real_open(self, name, *a, **kw)
    monkeypatch.setattr(zipfile.ZipFile, "open", spy_open)
    seen = []
    def classify(q):
        seen.append(q)
        assert opened and all(name.endswith("README.txt") for name in opened)
        return SearchDecision("lookup_unavailable", q, search_state="not_found")
    report = identify_archive(archive, classifier=classify, allow_metadata=True,
                              max_search_queries=3)
    assert seen and "Silver Lantern" in seen
    assert report.metadata.title_candidates == ("Silver Lantern",)
    assert report.inspection and "Star Runner" in report.inspection.title_candidates
    assert report.metadata.read_bytes > 0
    assert not any("Hidden " in q or "SECRET" in q for q in seen)
    assert len(opened) == 1


def test_v07_no_readme_does_not_open_member(tmp_path, monkeypatch):
    import zipfile
    path = make_zip(tmp_path, "Moon Voyage.zip", {
        "Moon Voyage/Game.exe": b"a",
        "Moon Voyage/game.json": b'{"gameTitle":"Do not open"}',
    })
    def cannot_open(*args, **kwargs):
        raise AssertionError("파일 목록만 검사해야 함")
    monkeypatch.setattr(zipfile.ZipFile, "open", cannot_open)
    out = identify_archive(
        path, classifier=lambda q: SearchDecision("lookup_unavailable", q),
        allow_metadata=True,
    )
    assert out.metadata.read_bytes == 0
    assert out.metadata.inspected_files == 0
    assert out.inspection is not None


def test_v07_filename_search_reservation_under_many_internal_codes(tmp_path):
    archive = make_zip(tmp_path, "Bright Summer Story.zip", {
        "RJ09999991/data.pak": b"x",
        "RJ09999992/engine.dll": b"x",
        "RJ09999993/plugin.dll": b"x",
        "Bright Summer Story/Bright Summer Story.exe": b"x",
    })
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    index = inspect_archive(archive)
    plan = build_search_plan(archive.name, index, None, max_queries=3)
    assert any(item.query == "Bright Summer Story" for item in plan)
    assert len(plan) <= 3
    observed = []
    identify_archive(
        archive, classifier=lambda q: (
            observed.append(q) or SearchDecision("confirmed_game", q,
                proposed_title="Official Synthetic",
                dlsite_code="RJ09999991")
        ) if q == "RJ09999991" else (
            observed.append(q) or SearchDecision("lookup_unavailable", q)
        ), allow_metadata=True, max_search_queries=3,
    )
    assert "Bright Summer Story" in observed


def test_v07_metadata_full_opt_in_still_available_for_legacy_research(tmp_path):
    from experiments.dlsite_detector.internal_metadata import (
        inspect_metadata, inspect_readme_metadata,
    )
    archive = make_zip(tmp_path, "Research Sample.zip", {
        "game/game.ini": b"Title=Deep Research Only",
        "game/README.txt": b"Game Title: Public Notes",
    })
    assert inspect_readme_metadata(archive).title_candidates == ("Public Notes",)
    legacy = inspect_metadata(archive)
    assert "Deep Research Only" in legacy.title_candidates
