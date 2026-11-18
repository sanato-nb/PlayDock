"""검색 실패 복구와 사용자 검증판 진행률 테스트 (실제 온라인 접속 없음)."""
from __future__ import annotations

from pathlib import Path
import zipfile

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.enhanced_search import enhanced_classify_game
from experiments.dlsite_detector.pipeline import SearchDecision, WebEvidence
from experiments.dlsite_detector.web_alias_discovery import discover_parallel_title
from experiments.dlsite_detector.identity_verifier import verify_identity


def hit(title, domain):
    return WebEvidence(
        title=title, url=f"https://{domain}/game",
        domain=domain, strong_match=False,
        game_context=True, trusted_source=False,
    )


def korean_alias_hits():
    return (
        hit("황성의 빅토리아스 Radiant Victorias ver1.0.1", "first.example"),
        hit("황성의 빅토리아스v1.0.1-전개방 Radiant Victorias", "second.example"),
    )


def mock_search(_title, *, code=""):
    return SearchDecision(
        "lookup_unavailable", _title, web_checked=True,
        evidence=korean_alias_hits(), reason="정확 일치 제목 없음",
    )


def test_two_independent_web_domains_preserve_unverified_english_alias():
    name="황성의 빅토리아스 [v1.0.1]"
    assert discover_parallel_title(name, korean_alias_hits()) == (
        "Radiant Victorias", ("first.example", "second.example"),
    )
    decision = enhanced_classify_game(
        name, classifier=mock_search,
        steam_fetcher=lambda *_: None,
    )
    assert decision.status == "internet_candidate"
    assert decision.proposed_title == "Radiant Victorias"
    assert not decision.source_id
    assert not decision.source_url
    assert "검증되지" in decision.reason


def test_one_source_or_duplicate_domain_does_not_make_alias():
    name="황성의 빅토리아스"
    one=(hit("황성의 빅토리아스 Radiant Victorias", "first.example"),)
    same=one + (hit("황성의 빅토리아스 Radiant Victorias", "first.example"),)
    assert discover_parallel_title(name, one) is None
    assert discover_parallel_title(name, same) is None


def test_multiple_competing_english_aliases_fail_closed():
    name="황성의 빅토리아스"
    records=(
        hit("황성의 빅토리아스 Radiant Victorias", "a.example"),
        hit("황성의 빅토리아스 Radiant Victorias", "b.example"),
        hit("황성의 빅토리아스 Unknown Game", "c.example"),
        hit("황성의 빅토리아스 Unknown Game", "d.example"),
    )
    assert discover_parallel_title(name, records) is None


def test_unrelated_english_title_does_not_rescue_local_title():
    name="황성의 빅토리아스"
    records=(
        hit("Another Korean Game Radiant Victorias", "a.example"),
        hit("Another Korean Game Radiant Victorias", "b.example"),
    )
    assert discover_parallel_title(name, records) is None


def test_local_english_game_names_not_altered():
    records=(
        hit("Radiant Victorias Radiant Victorias", "a.example"),
        hit("Radiant Victorias Radiant Victorias", "b.example"),
    )
    assert discover_parallel_title("Radiant Victorias", records) is None


def test_alias_discovery_is_candidate_not_game_confirmation(tmp_path):
    path=tmp_path/"황성의 빅토리아스 [v1.0.1].zip"
    with zipfile.ZipFile(path, "w") as arc:
        arc.writestr("Game/game.exe", b"sample")
    def classify(query):
        return enhanced_classify_game(
            query, classifier=mock_search,
            steam_fetcher=lambda *_: None,
        )
    report=identify_archive(path, classifier=classify, allow_metadata=True)
    assert report.status == "candidate_found"
    assert report.proposed_title == "Radiant Victorias"
    verified=verify_identity(report)
    assert verified.verdict == "needs_review"
    assert not verified.automatic_binding_allowed


def test_pipeline_calls_steps_in_order_and_callback_is_optional(tmp_path):
    path=tmp_path/"Ordinary.zip"
    with zipfile.ZipFile(path,"w") as arc:
        arc.writestr("Game/Game.ini", "Title=Ordinary Story\n")
    events=[]
    report=identify_archive(
        path, classifier=lambda q: SearchDecision(
            "internet_candidate", q, proposed_title="Ordinary Story",
        ),
        allow_metadata=True,
        progress_callback=lambda step,label: events.append((step,label)),
    )
    assert report.completed_steps == (1,2,3,4,5)
    assert [step for step,_ in events] == [1,2,3,4,5]

    # 잘못된 UI 콜백이 작품 판정/파일 검사 자체를 중단하면 안 된다.
    other=identify_archive(
        path, classifier=lambda q: SearchDecision(
            "internet_candidate",q,proposed_title="Ordinary Story",
        ),
        allow_metadata=True,
        progress_callback=lambda *_: 1/0,
    )
    assert other.status == report.status


def test_offline_progress_percentage_is_bounded_without_gui_window():
    from scripts.game_identity_tester import IdentityTesterApp

    class FakeValue:
        def __init__(self):
            self.value=None
        def set(self,value):
            self.value=value
    class FakeBar:
        def __init__(self):
            self.value=None
        def configure(self, **kwargs):
            self.value=kwargs.get("value")

    obj=object.__new__(IdentityTesterApp) if False else None
    # Tk.__new__ produces an uninitialized wrapper; helper only touches mocks.
    class Dummy:
        _show_progress=IdentityTesterApp._show_progress
        paths=list(range(128))
        bar=FakeBar()
        progress=FakeValue()
        running_online=True
    test=Dummy()
    test._show_progress(3, 4)
    assert 2.3 < test.bar.value < 3.0
    assert "3 / 128개" in test.progress.value
    test._show_progress(128,1)
    assert test.bar.value == 100
