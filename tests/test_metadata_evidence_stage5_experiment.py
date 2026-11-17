"""PlayDock 5단계: 엔진별 제목 필드, 근거 등급, 출처 및 오탐 차단 회귀 검사."""
from __future__ import annotations

import json
import zipfile

import pytest

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.internal_metadata import inspect_metadata
from experiments.dlsite_detector.metadata_fields import parse_metadata_fields
from experiments.dlsite_detector.pipeline import SearchDecision


def create_zip(tmp_path, entries, name="Unknown.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        for filename, value in entries.items():
            archive.writestr(filename, value)
    return path


def title_evidence(result, title):
    return [e for e in result.evidence
            if e.kind == "title" and e.candidate_title == title]


@pytest.mark.parametrize("location", (
    "Project/data/System.json",
    "Project/www/data/System.json",
))
def test_rpg_maker_mv_mz_system_game_title_is_strong(location, tmp_path):
    archive = create_zip(tmp_path, {
        location: json.dumps({"gameTitle": "Moonlit Trail", "name": "INTERNAL_PACKAGE"}),
        "Project/Game.exe": b"fake",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Moonlit Trail",)
    assert result.strong_titles == ("Moonlit Trail",)
    assert title_evidence(result, "Moonlit Trail")[0].parser == "rpg_maker_mv_mz"
    assert "INTERNAL_PACKAGE" not in str(result.to_dict())


def test_rpg_maker_system_json_in_unrelated_path_is_not_title(tmp_path):
    archive = create_zip(tmp_path, {
        "Unrelated/System.json": '{"gameTitle":"Wrong Title"}',
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ()
    assert result.strong_titles == ()


def test_godot_application_name_only_not_editor_project_section(tmp_path):
    archive = create_zip(tmp_path, {
        "Release/project.godot":
            "[editor]\nconfig/name=\"Wrong Title\"\n"
            "[application]\nconfig/name=\"Star Chamber\"\n"
            "run/main_scene=\"res://main.tscn\"\n"
            "[rendering]\nconfig/name=\"Wrong Too\"\n",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Star Chamber",)
    assert result.strong_titles == ("Star Chamber",)
    item = title_evidence(result, "Star Chamber")[0]
    assert item.member == "Release/project.godot"
    assert item.field == "application.config/name"
    assert item.strength == "strong"
    assert item.parser == "godot"


def test_renpy_config_name_and_rpg_maker_game_ini_independent_evidence(tmp_path):
    archive = create_zip(tmp_path, {
        "Novel/game/options.rpy": 'define config.name = _("A Summer Story")\n',
        "Novel/Game.ini": "[Game]\nTitle=A Summer Story\n",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("A Summer Story",)
    assert len(title_evidence(result, "A Summer Story")) == 2
    assert {x.parser for x in title_evidence(result, "A Summer Story")} == {
        "renpy", "game_ini",
    }


def test_unity_company_name_is_not_game_title(tmp_path):
    archive = create_zip(tmp_path, {
        "Mystery_Data/app.info": "Studio Orion\nOrbit Harvest\n",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Orbit Harvest",)
    assert result.strong_titles == ("Orbit Harvest",)
    assert any(e.kind == "publisher" and e.candidate_title == "Studio Orion"
               for e in result.evidence)
    assert "Studio Orion" not in result.title_candidates


def test_json_name_fields_are_not_trusted_game_titles(tmp_path):
    archive = create_zip(tmp_path, {
        "Project/metadata.json": '{"name":"SPOOFED_GAME", "password":"x"}',
        "Project/version.json": '{"name":"RELEASE_PIPELINE"}',
        "Project/package.json": '{"name":"internal.nw.package", "version":"1.1"}',
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ()
    assert result.strong_titles == ()
    assert any(e.kind == "project_name" and e.strength == "weak"
               for e in result.evidence)
    assert "SPOOFED_GAME" not in str(result.to_dict())
    assert "RELEASE_PIPELINE" not in str(result.to_dict())


def test_nwjs_window_title_is_supporting_and_package_name_is_weak(tmp_path):
    archive = create_zip(tmp_path, {
        "Project/package.json": json.dumps({
            "name": "internal_project", "window": {"title": "Woodland Mystery"},
            "author": "secret@example.com", "access_token": "DO_NOT_DISCLOSE",
        }),
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Woodland Mystery",)
    assert result.strong_titles == ()
    assert title_evidence(result, "Woodland Mystery")[0].strength == "supporting"
    assert any(e.kind == "project_name" and e.strength == "weak"
               for e in result.evidence)
    assert "DO_NOT_DISCLOSE" not in str(result.to_dict())
    assert "secret@example.com" not in str(result.to_dict())


def test_readme_title_remains_search_candidate_but_does_not_force_conflict(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/Game.exe": "binary",
        "Game/README.txt": "Game Title: Translation Pack\nPassword: SECRET\n",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Translation Pack",)
    assert result.strong_titles == ()
    assert title_evidence(result, "Translation Pack")[0].strength == "supporting"
    def external(_):
        return SearchDecision("platform_confirmed_game", "Game",
                              proposed_title="Original Story")
    report = identify_archive(archive, classifier=external, allow_metadata=True)
    assert report.status == "candidate_found"
    assert report.evidence_conflict is False
    assert report.metadata.strong_titles == ()


def test_explicit_strong_game_ini_conflict_still_requests_review(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/Game.ini": "Title=Different Story\n",
    })
    report = identify_archive(
        archive,
        classifier=lambda _: SearchDecision(
            "platform_confirmed_game", "Unknown", proposed_title="Other Story",
        ),
        allow_metadata=True,
    )
    assert report.status == "ambiguous"
    assert report.evidence_conflict is True


def test_engine_priority_wins_over_many_readme_files(tmp_path):
    entries = {f"Extras/README_{i:02d}.txt": "Game Title: Side Info"
               for i in range(30)}
    # All entries exist but only a small amount will be read.
    entries["Core/Game.ini"] = "Title=Actual Title"
    archive = create_zip(tmp_path, entries)
    result = inspect_metadata(archive)
    assert result.strong_titles == ("Actual Title",)
    assert result.title_candidates[0] == "Actual Title"
    assert result.inspected_files <= 8


def test_explicit_product_code_keeps_source_and_strength(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/metadata.json": json.dumps({
            "dlsite_code": "RJ01234567", "gameTitle": "Spring Story",
        }),
        "Game/readme.txt": "품번: RJ01234567\n",
    })
    result = inspect_metadata(archive)
    assert result.product_codes == ("RJ01234567",)
    codes = [e for e in result.evidence if e.kind == "product_code"]
    assert len(codes) == 2
    assert all(e.strength == "strong" for e in codes)
    assert {e.member for e in codes} == {
        "Game/metadata.json", "Game/readme.txt",
    }


def test_binary_and_secret_material_is_not_parsed_as_title(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/Game.exe": b"Title=WRONG\x00\x01",
        "Game/metadata.json": '{"title":"https://private.example","token":"secret"}',
        "Game/readme.txt": "Title: somebody@example.com\n"
                           "Title: Real Story\n",
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ("Real Story",)
    assert "secret" not in str(result.to_dict())
    assert "private.example" not in str(result.to_dict())


def test_ineligible_json_data_never_becomes_title_and_does_not_execute(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/game.json": '{"name": "Not Game", "script": "__import__(\"os\")"}',
        "Game/metadata.json": '{"metadata":{"title":"Hidden Secret"}}',
    })
    result = inspect_metadata(archive)
    assert result.title_candidates == ()
    assert result.strong_titles == ()


def test_result_json_includes_individual_evidence_provenance(tmp_path):
    archive = create_zip(tmp_path, {
        "Game/Game.ini": "Title=Star Chamber\n",
    })
    report = inspect_metadata(archive).to_dict()
    assert list(report["evidence"]) == [{
        "member": "Game/Game.ini",
        "field": "Title",
        "candidate_title": "Star Chamber",
        "kind": "title",
        "strength": "strong",
        "parser": "game_ini",
    }]
