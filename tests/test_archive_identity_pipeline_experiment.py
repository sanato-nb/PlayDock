"""압축파일 이름 검색 → 내부 목록 근거 재검색의 독립 통합 회귀 테스트.

검색은 주입된 모의 함수만 호출하며 파일을 압축 해제하거나 실행하지 않는다.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector import identify_cli


def archive(tmp_path, filename="Unknown_Game.zip", entries=()):
    path = tmp_path / filename
    with zipfile.ZipFile(path, "w") as zf:
        for name in entries:
            zf.writestr(name, b"SAFE")
    return path


def found(query, *, code=""):
    return SearchDecision(
        "internet_confirmed_game", query, proposed_title=query,
        dlsite_status="unverified", dlsite_code=code,
        reason="모의 외부 독립 출처 두 곳에서 일치",
    )


def missing(query):
    return SearchDecision("lookup_unavailable", query, reason="모의 검색 실패", web_checked=True)


def test_stage1_success_still_scans_non_encrypted_index(tmp_path):
    from experiments.dlsite_detector.archive_inspector import inspect_archive
    path = archive(tmp_path, entries=["ABC/ABC.exe"])
    calls, inspected = [], []
    def classifier(query):
        calls.append(query)
        return found("Original Verified")
    def inspector(value):
        inspected.append(value)
        return inspect_archive(value)
    result = identify_archive(path, classifier=classifier, inspector=inspector)
    assert inspected == [path]
    assert calls[0] == "Unknown Game"
    assert result.execution_order == (1, 3, 4, 2)
    assert result.status == "candidate_found" and result.stage == 1
    assert result.inspection.member_count == 1
    assert result.completed_steps == (1, 2, 3, 4)
    assert result.to_dict()["external_status"] == "internet_confirmed_game"


def test_stage1_dlsite_non_game_stays_separate(tmp_path):
    path = archive(tmp_path)
    result = identify_archive(
        path,
        classifier=lambda q: SearchDecision("suspected_non_game", q, proposed_title="음성 작품"),
    )
    assert result.status == "suspected_non_game" and result.stage == 1
    assert result.inspection.state == "ok"


def test_stage1_failure_uses_internal_exe_to_search_again(tmp_path):
    path = archive(tmp_path, entries=[
        "Actual Story/Actual Story.exe",
        "Actual Story/Actual Story_Data/level0",
        "Actual Story/docs/README.txt",
    ])
    original = path.read_bytes()
    calls = []
    def classifier(query):
        calls.append(query)
        return found(query) if query == "Actual Story" else missing(query)

    result = identify_archive(path, classifier=classifier)
    assert result.status == "candidate_found" and result.stage == 2
    assert result.proposed_title == "Actual Story"
    assert calls == ["Unknown Game", "Actual Story"]
    assert result.inspection is not None
    assert "Unity" in result.inspection.engine_hints
    assert "미확정" in result.reason
    assert path.read_bytes() == original


def test_stage2_candidate_is_not_falsely_auto_confirmed(tmp_path):
    path = archive(tmp_path, entries=["Another Game/Another Game.exe"])
    result = identify_archive(
        path, classifier=lambda q: found(q) if q == "Another Game" else missing(q))
    assert result.status == "candidate_found"
    assert result.status != "confirmed_game"


def test_stage2_uses_internal_dlsite_code_as_manual_candidate(tmp_path):
    path = archive(tmp_path, entries=[
        "game.exe", "data/notes_RJ01081508.txt",
    ])
    calls = []
    def classifier(query):
        calls.append(query)
        return (SearchDecision("confirmed_game", query, proposed_title="정식 게임",
                               dlsite_status="confirmed_game", dlsite_code="RJ01081508")
                if query == "RJ01081508" else missing(query))
    result = identify_archive(path, classifier=classifier)
    assert result.status == "candidate_found" and result.stage == 2
    assert result.product_code == "RJ01081508"
    assert calls == ["RJ01081508"]  # 공식 ID 확인 후 중복 약한 제목 검색 생략
    assert result.inspection.product_codes == ("RJ01081508",)


def test_conflicting_internal_names_result_in_ambiguity(tmp_path):
    path = archive(tmp_path, entries=["Alpha Project/Alpha Project.exe", "Beta Project/Beta Project.exe"])
    def classifier(query):
        return found(query) if query in ("Alpha Project", "Beta Project") else missing(query)
    result = identify_archive(path, classifier=classifier)
    assert result.status == "ambiguous"
    assert result.proposed_title == ""
    assert len(result.attempts) == 3


def test_all_attempts_fail_end_in_unresolved(tmp_path):
    path = archive(tmp_path, entries=["A/Distinct Name.exe"])
    result = identify_archive(path, classifier=missing)
    assert result.status == "lookup_unavailable"
    assert result.stage == 2
    assert len(result.attempts) == 2


def test_generic_or_no_internal_candidates_do_not_repeat_requests(tmp_path):
    path = archive(tmp_path, entries=["game.exe", "Data/launcher.exe"])
    called = []
    def classifier(query):
        called.append(query)
        return missing(query)
    result = identify_archive(path, classifier=classifier)
    assert result.status == "lookup_unavailable"
    assert called == ["Unknown Game"]


def test_duplicate_internal_title_matching_filename_does_not_repeat(tmp_path):
    path = archive(tmp_path, filename="My Game.zip", entries=["My Game/My Game.exe"])
    called = []
    def classifier(query):
        called.append(query)
        return missing(query)
    result = identify_archive(path, classifier=classifier)
    assert result.status == "lookup_unavailable"
    assert called == ["My Game"]


def test_archive_path_not_sent_to_searcher(tmp_path):
    private = tmp_path / "Private Folder"
    private.mkdir()
    path = archive(private, filename="Unknown_Game.zip", entries=["Unlisted Title/Unlisted Title.exe"])
    called = []
    result = identify_archive(path, classifier=lambda q: called.append(q) or missing(q))
    assert result.stage == 2
    assert called == ["Unknown Game", "Unlisted Title"]
    assert all(str(tmp_path) not in q and "/" not in q and "\\" not in q for q in called)


def test_cannot_open_missing_or_unsupported_archive(tmp_path):
    for p in (tmp_path / "missing.zip", tmp_path / "manual.exe"):
        result = identify_archive(
            p, classifier=lambda q: pytest.fail("존재하지 않는 압축파일은 검색 금지"))
        assert result.status == "invalid_archive" and result.stage == 0


def test_corrupt_archive_after_failed_search_is_unresolved(tmp_path):
    path = tmp_path / "corrupt.zip"
    path.write_bytes(b"broken zip")
    result = identify_archive(path, classifier=missing)
    assert result.status == "lookup_unavailable"
    assert result.stage == 2
    assert result.inspection.state == "unavailable"


def test_bounded_search_attempts_from_many_internal_files(tmp_path):
    entries = [f"Game Title {i}/Game Title {i}.exe" for i in range(20)]
    entries += [f"RJ0108150{i}.txt" for i in range(10)]
    path = archive(tmp_path, entries=entries)
    called = []
    result = identify_archive(path, classifier=lambda q: called.append(q) or missing(q))
    assert result.status == "lookup_unavailable"
    assert len(called) <= 1 + 4 + 2


def test_no_member_read_or_unzip_while_searching(tmp_path, monkeypatch):
    path = archive(tmp_path, entries=["Secret Demo/Secret Demo.exe"])
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *_a, **_k: pytest.fail("unzip forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda *_a, **_k: pytest.fail("unzip forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *_a, **_k: pytest.fail("member reading forbidden"))
    assert identify_archive(path, classifier=missing).stage == 2


def test_cli_offline_default_makes_no_internet_requests(tmp_path, monkeypatch, capsys):
    path = archive(tmp_path, entries=["Example Project/Example Project.exe"])
    monkeypatch.setattr(identify_cli, "identify_archive",
                        lambda *_a: pytest.fail("offline mode must not search"))
    assert identify_cli.main([str(path), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "offline_inventory"
    assert "Example Project" in output["title_candidates"]


def test_cli_online_invokes_full_pipeline(tmp_path, monkeypatch, capsys):
    path = archive(tmp_path)
    monkeypatch.setattr(identify_cli, "identify_archive",
                        lambda _, **kw: identify_archive(path, classifier=missing, **kw))
    assert identify_cli.main([str(path), "--online", "--json"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["stage"] == 3
    assert output["completed_steps"] == [1, 2, 3, 4, 5]
    assert output["inspection_complete"] is True
    assert output["status"] == "lookup_unavailable"
    assert output["label"].startswith("정체 조회 불가")
