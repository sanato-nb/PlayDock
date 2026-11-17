"""게임 정체 검색 품질 실험: 버전 제거, 언어별 검색, 후보 중복·오탐 방지."""
from __future__ import annotations

import sys
import types
import zipfile

import pytest

from experiments.dlsite_detector.detector import (
    Detection, Product, detect_dlsite_game, normalized_title,
)
from experiments.dlsite_detector.pipeline import (
    SearchDecision, classify_game, default_web_search,
)
from experiments.dlsite_detector.search_terms import (
    archive_basename, cleaned_search_title, search_title_variants,
)
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.review_store import ReviewStore


def missing(title, *, code="", allow_title_search=False):
    return Detection("unverified", title, reason="검색할 작품 코드 없음")


def web_link(title, host, path):
    return {
        "title": title + " - Game",
        "href": f"https://{host}/{path}",
        "body": "PC video game",
    }


def test_filename_cleanup_keeps_series_and_removes_version_tags():
    assert cleaned_search_title("PASEC_v2.2566.zip") == "PASEC"
    assert cleaned_search_title("D:\\Secret\\PASEC_v2.2566.7z") == "PASEC"
    assert cleaned_search_title("My_Game [RJ01081508] [v1.20] [한글패치].rar") == "My Game"
    assert cleaned_search_title("Game 2 [한국어 번역].zip") == "Game 2"
    assert cleaned_search_title("Project III (v2.10)") == "Project III"
    assert cleaned_search_title("Game_2") == "Game 2"
    assert cleaned_search_title("Game_3") == "Game 3"
    assert normalized_title("Game 2") != normalized_title("Game 3")


def test_filename_variants_are_bounded_and_keep_original_as_fallback():
    assert search_title_variants("PASEC_v2.2566.zip") == ("PASEC", "PASEC_v2.2566")
    assert search_title_variants("Test Game") == ("Test Game",)
    assert search_title_variants("Test Game", limit=1) == ("Test Game",)
    assert archive_basename("C:\\private\\My Game.zip") == "My Game"
    assert search_title_variants("RJ01081508.zip") == ("RJ01081508",)


def test_dlsite_search_tries_clean_title_without_faking_product_code():
    searched = []
    link = "https://www.dlsite.com/maniax/work/=/product_id/RJ01081508.html"
    def searcher(query):
        searched.append(query)
        return [{"href": link}] if query == "My Game" else []
    def fetcher(code):
        assert code == "RJ01081508"
        return Product(code, "My Game", "RPG", "maniax", link)
    result = detect_dlsite_game(
        "My_Game_v1.0", allow_title_search=True, searcher=searcher, fetcher=fetcher)
    assert searched[0] == "My Game"
    assert result.status == "confirmed_game"
    assert result.work_title == "My Game"


def test_web_search_variants_merge_sources_but_only_propose_candidate():
    searched = []
    def web(query):
        searched.append(query)
        if query == "My Game":
            return [web_link("My Game", "store.steampowered.com", "app/100/mygame")]
        if query == "My_Game_v1.0":
            return [web_link("My Game", "www.gog.com", "en/game/mygame")]
        return []
    result = classify_game("My_Game_v1.0.zip", dlsite_lookup=missing, web_search=web)
    assert searched == ["My Game", "My_Game_v1.0"]
    assert result.status == "internet_candidate"
    assert len(result.evidence) == 2
    assert result.proposed_title == "My Game"
    assert "수동 또는 원문 검증" in result.reason


def test_search_results_from_two_sites_are_not_trusted_as_verified_pages():
    result = classify_game("My Game", dlsite_lookup=missing, web_search=lambda _: [
        web_link("My Game", "store.steampowered.com", "app/100/mygame"),
        web_link("My Game", "www.gog.com", "en/game/mygame"),
    ])
    assert result.status == "internet_candidate"
    assert "후보" in result.label
    assert result.web_checked is True


def test_similar_sequel_does_not_match_different_game():
    result = classify_game("My Game 2", dlsite_lookup=missing, web_search=lambda _: [
        web_link("My Game", "store.steampowered.com", "app/100/mygame"),
        web_link("My Game", "www.gog.com", "en/game/mygame"),
    ])
    assert result.status == "lookup_unavailable"
    assert all(not evidence.strong_match for evidence in result.evidence)


def test_one_source_does_not_become_confirmed_even_after_fallback():
    result = classify_game("My_Game_v2.1", dlsite_lookup=missing, web_search=lambda _: [
        web_link("My Game", "store.steampowered.com", "app/100/mygame")
    ])
    assert result.status == "lookup_unavailable"
    assert len(result.evidence) == 1


def test_default_web_search_korean_uses_localized_and_exact_fallback(monkeypatch):
    queries = []
    class FakeDDGS:
        def __init__(self, timeout):
            assert timeout <= 12
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def text(self, phrase, max_results):
            queries.append(phrase)
            assert max_results <= 8
            return [web_link("한국어 게임", "www.gog.com", "en/game/ko")]
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    hits = default_web_search("한국어 게임")
    assert queries == ['"한국어 게임" 게임', '"한국어 게임"']
    assert len(hits) == 1  # 두 검색식에서 같은 URL은 합치기


def test_default_web_search_japanese_uses_japanese_keyword(monkeypatch):
    queries = []
    class FakeDDGS:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def text(self, phrase, max_results):
            queries.append(phrase)
            return []
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    assert default_web_search("日本語作品") == []
    assert queries[0] == '"日本語作品" ゲーム'


def test_default_web_search_fallback_survives_first_search_error(monkeypatch):
    class FakeDDGS:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def text(self, phrase, max_results):
            if phrase.endswith(" game"):
                raise TimeoutError("first search timeout")
            return [web_link("Test Game", "www.gog.com", "en/game/test")]
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    assert len(default_web_search("Test Game")) == 1


def test_archive_stage1_web_candidate_does_not_force_archive_inspection(tmp_path):
    path = tmp_path / "Candidate_v1.2.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Completely Unrelated/Other.exe", b"content")
    def classifier(query):
        return SearchDecision("internet_candidate", query, proposed_title="Candidate")
    result = identify_archive(path, classifier=classifier,
                              inspector=lambda _: pytest.fail("1단계 후보 발견 후 자동 내부 분석 금지"))
    assert result.status == "candidate_found"
    assert result.stage == 1
    assert result.inspection is None


def test_archive_stage2_web_candidate_requires_manual_confirmation(tmp_path):
    path = tmp_path / "Unknown.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Real Game/Real Game.exe", b"sample")
    def classifier(query):
        if query == "Real Game":
            return SearchDecision("internet_candidate", query, proposed_title="Real Game")
        return SearchDecision("lookup_unavailable", query)
    result = identify_archive(path, classifier=classifier)
    assert result.status == "candidate_found" and result.stage == 2
    assert "수동 확인" in result.reason


def test_review_db_saves_web_candidate_without_auto_changing_title(tmp_path):
    store = ReviewStore(tmp_path / "experiment.db")
    store.add_game("g1", "Old Game Name", "Old Game Name.zip")
    candidate = SearchDecision("internet_candidate", "Old Game Name",
                               proposed_title="Found New Name", web_checked=True)
    store.save_search_result("g1", candidate)
    stored = store.get_game("g1")
    assert stored["classification"] == "internet_candidate"
    assert stored["display_name"] == stored["original_name"] == "Old Game Name"
    assert store.search_history("g1")[0]["proposed_title"] == "Found New Name"
