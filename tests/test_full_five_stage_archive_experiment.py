"""1~5단계 전수 목록/선택적 메타데이터 검증 회귀 실험."""
from __future__ import annotations

import json
import zipfile

from experiments.dlsite_detector import archive_inspector, identify_cli
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.pipeline import SearchDecision


def zip_archive(tmp_path, name="Test Story.zip", entries=None):
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as out:
        for filename, data in (entries or {}).items():
            out.writestr(filename, data)
    return archive


def external_confirmed(query):
    return SearchDecision("platform_confirmed_game", query,
                          proposed_title="Test Story",
                          source_platform="steam", source_id="12345")


def external_candidate(query):
    return SearchDecision("internet_candidate", query,
                          proposed_title="Test Story")


def test_title_success_always_inspects_all_members_and_selected_metadata(tmp_path):
    archive = zip_archive(tmp_path, entries={
        "Test Story/Test Story.exe": b"sample exe",
        "Test Story/Test Story_Data/data": b"binary",
        "Test Story/Game.ini": "Title=Test Story\n",
        "Test Story/readme.txt": "Game title: Test Story\n",
    })
    original = archive.read_bytes()
    result = identify_archive(archive, classifier=external_confirmed, allow_metadata=True)
    assert result.status == "candidate_found", "로컬 게임 동일성은 아직 확정하면 안 됨"
    assert result.stage == 1, "후보의 출처는 파일명이며 실행 완료 단계와 다름"
    assert result.completed_steps == (1, 2, 3, 4, 5)
    assert result.inspection.member_count == 4
    assert result.inspection.state == "ok"
    assert result.to_dict()["inspection_complete"] is True
    assert result.metadata.title_candidates == ("Test Story",)
    assert result.to_dict()["external_status"] == "platform_confirmed_game"
    assert archive.read_bytes() == original


def test_title_search_success_but_inner_title_disagrees_is_not_confirmed(tmp_path):
    archive = zip_archive(tmp_path, entries={
        "Game/Game.ini": "Title=Different Story\n",
        "Game/game.exe": b"bin",
    })
    result = identify_archive(archive, classifier=external_confirmed, allow_metadata=True)
    assert result.status == "ambiguous"
    assert result.evidence_conflict
    assert result.completed_steps == (1, 2, 3, 4, 5)
    assert result.metadata.title_candidates == ("Different Story",)
    assert result.inspection.member_count == 2
    assert result.proposed_title == ""


def test_title_success_without_internal_title_remains_candidate(tmp_path):
    archive = zip_archive(tmp_path, entries={
        "Game/game.exe": b"something",
        "Game/data.pak": b"something else",
    })
    result = identify_archive(archive, classifier=external_confirmed, allow_metadata=True)
    assert result.status == "candidate_found"
    assert result.metadata.state == "no_metadata"
    assert result.completed_steps == (1, 2, 3, 4, 5)


def test_title_search_candidate_does_not_avoid_internal_index(tmp_path):
    archive = zip_archive(tmp_path, entries={
        "Other/Other.exe": b"something",
        "Other/Game.ini": "Title=Other Story\n",
    })
    result = identify_archive(archive, classifier=external_candidate, allow_metadata=True)
    assert result.inspection.member_count == 2
    assert result.status == "ambiguous"


def test_optional_metadata_can_be_disabled_but_index_still_inspected(tmp_path):
    archive = zip_archive(tmp_path, entries={
        "Test Story/Test Story.exe": b"sample",
        "Test Story/Game.ini": "Title=Test Story\n",
    })
    result = identify_archive(
        archive, classifier=external_confirmed, allow_metadata=False,
        metadata_reader=lambda *_: (_ for _ in ()).throw(
            AssertionError("no metadata read when disabled")),
    )
    assert result.status == "candidate_found"
    assert result.inspection.member_count == 2
    assert result.metadata is None
    assert result.completed_steps == (1, 2, 3, 4)


def test_index_limit_is_reported_as_incomplete_not_full_scan(tmp_path, monkeypatch):
    archive = zip_archive(tmp_path, entries={
        f"Test Story/asset-{i}.bin": b"x" for i in range(10)
    })
    monkeypatch.setattr(archive_inspector, "MAX_MEMBERS", 3)
    result = identify_archive(archive, classifier=external_confirmed, allow_metadata=True)
    assert result.inspection.state == "limit_exceeded"
    assert result.to_dict()["inspection_complete"] is False
    assert "전체 목록은 미검사" in result.reason
    assert result.completed_steps == (1, 2, 3, 4, 5)


def test_online_cli_runs_five_steps_by_default(tmp_path, monkeypatch, capsys):
    archive = zip_archive(tmp_path, entries={
        "Test Story/Game.ini": "Title=Test Story\n",
    })
    observed = []
    def fake_identify(path, **kwargs):
        observed.append(kwargs)
        return identify_archive(path, classifier=external_confirmed, **kwargs)
    monkeypatch.setattr(identify_cli, "identify_archive", fake_identify)
    assert identify_cli.main([str(archive), "--online", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert observed == [{"allow_metadata": True}]
    assert output["completed_steps"] == [1, 2, 3, 4, 5]
    assert output["metadata"]["title_candidates"] == ["Test Story"]


def test_online_cli_supports_no_metadata_opt_out(tmp_path, monkeypatch, capsys):
    archive = zip_archive(tmp_path, entries={"Some/Game.ini": "Title=Test Story"})
    observed = []
    def fake_identify(path, **kwargs):
        observed.append(kwargs)
        return identify_archive(path, classifier=external_confirmed, **kwargs)
    monkeypatch.setattr(identify_cli, "identify_archive", fake_identify)
    assert identify_cli.main([str(archive), "--online", "--no-metadata", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert observed == [{}]
    assert output["completed_steps"] == [1, 2, 3, 4]
    assert output["metadata"] is None
