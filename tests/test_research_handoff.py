"""Excluded → AI JSON handoff → official verification → safe rename/undo."""
import json
from pathlib import Path

import pytest

from experiments.dlsite_detector.code_only import Result
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.steam_client import SteamProduct
from experiments.dlsite_detector.research_handoff import (
    SCHEMA, ResearchSuggestion, excluded_from_results, research_export,
    research_prompt, read_ai_response, reverify, proposed_filename,
    safe_rename, undo_last, load_previous_excluded,
)


def fake_dl(code):
    return Product(code, "Original Japanese Title", "", "maniax",
                   "https://www.dlsite.com/maniax/work/=/product_id/" + code + ".html")


def fake_steam(appid):
    return SteamProduct(appid, "Official Steam Game", "game",
                        "https://store.steampowered.com/app/" + appid + "/")


def sample(filename="Game [v1.2] [한글패치].7z", code="RJ123456",
           store="dlsite", verification="official_confirmed", **extra):
    url = (f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html"
           if store == "dlsite"
           else f"https://store.steampowered.com/app/{code}/")
    return {"original_filename": filename, "store": store, "code": code,
            "official_title": "Title", "official_url": url,
            "verification": verification, "note": "제작자와 시리즈 대조", **extra}


def write_ai(tmp_path, rows, schema=SCHEMA):
    p = tmp_path / "ai.json"
    p.write_text(json.dumps({"schema": schema, "results": rows},
                            ensure_ascii=False), encoding="utf-8")
    return p


def test_only_excluded_exported_no_paths_or_confirmed_entries():
    rows = [
        Result("Game [v1.2] [한글패치].7z", "archive", "excluded"),
        Result("Other [RJ123456].zip", "archive", "confirmed"),
        Result("DL fail [RJ654321].zip", "archive", "excluded"),
    ]
    data = research_export(rows)
    assert len(data["excluded"]) == 2
    assert data["excluded"][0]["exclusion_reason"] == "no_identifier"
    assert data["excluded"][1]["exclusion_reason"] == "official_lookup_failed"
    assert data["excluded"][1]["dlsite_codes"] == ["RJ654321"]
    assert "C:\\Users" not in json.dumps(data, ensure_ascii=False)
    assert "absolute_path" not in json.dumps(data, ensure_ascii=False).lower()
    assert "original_filename" in research_prompt()
    assert "playdock-ai-review-v1" in research_prompt()


def test_old_result_json_loader_uses_only_excluded_and_basename(tmp_path):
    obj = {"results": [
        {"query": "Missing Game.zip", "status": "excluded",
         "input_origin": "archive", "attempted_stores": [],
         "warnings": ["없음"]},
        {"query": "Valid [RJ123456].zip", "status": "confirmed"},
        {"query": "C:/SecretFolder/Evil.zip", "status": "excluded"},
    ]}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    rows = load_previous_excluded(path)
    assert len(rows) == 1
    assert rows[0].query == "Missing Game.zip"
    assert len(excluded_from_results(rows)) == 1


def test_valid_ai_result_requires_matching_excluded_filename(tmp_path):
    allowed = ["Game [v1.2] [한글패치].7z"]
    file = write_ai(tmp_path, [sample(), sample(filename="Not in list.zip")])
    rows, warnings = read_ai_response(file, allowed)
    assert len(rows) == 1
    assert len(warnings) == 1
    assert rows[0].store == "dlsite"
    assert rows[0].code == "RJ123456"


def test_ai_result_ignores_unknown_candidate_without_code(tmp_path):
    file = write_ai(tmp_path, [
        sample(verification="candidate"),
        sample(filename="Second Game.zip", code="", verification="unknown"),
    ])
    rows, warnings = read_ai_response(file, ["Game [v1.2] [한글패치].7z", "Second Game.zip"])
    assert len(rows) == 1
    assert rows[0].verification == "candidate"
    assert not warnings
    v = reverify(rows[0], dlsite_check=lambda code: (_ for _ in ()).throw(
        AssertionError("AI 후보는 official_confirmed 전까지 네트워크 재검증 안 함")))
    assert not v.verified


@pytest.mark.parametrize("row", [
    sample(store="steam", code="1091500", official_url="https://evil.example"),
    sample(code="RJ654321", official_url="https://evil.example"),
    sample(code="BADNUMBER"),
    sample(filename="../Game.zip"),
    sample(filename="Game [v1.2] [한글패치].7z", code="1091500"),
])
def test_untrusted_ai_invalid_input_never_becomes_candidate(tmp_path, row):
    file = write_ai(tmp_path, [row])
    rows, problems = read_ai_response(file, ["Game [v1.2] [한글패치].7z"])
    assert rows == []
    assert problems


def test_invalid_schema_raises(tmp_path):
    file = write_ai(tmp_path, [sample()], schema="any-random-json")
    with pytest.raises(ValueError):
        read_ai_response(file, ["Game [v1.2] [한글패치].7z"])


def test_ai_matching_code_must_be_reverified_from_official_page():
    s = ResearchSuggestion("Game [v1.2] [한글패치].7z", "dlsite", "RJ123456",
                           "English Title",
                           "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                           verification="official_confirmed")
    good = reverify(s, dlsite_check=lambda code: fake_dl(code))
    assert good.verified
    assert good.official_title == "Original Japanese Title"
    wrong = reverify(s, dlsite_check=lambda code: fake_dl("RJ654321"))
    assert not wrong.verified
    blocked = reverify(s, dlsite_check=lambda code: None)
    assert not blocked.verified


def test_steam_reverify_validates_number_and_official_url():
    s = ResearchSuggestion("Steam Game.zip", "steam", "1091500",
                           "Official Steam Game",
                           "https://store.steampowered.com/app/1091500/",
                           verification="official_confirmed")
    good = reverify(s, steam_check=lambda code: fake_steam(code))
    assert good.verified and good.official_title == "Official Steam Game"
    wrong = reverify(s, steam_check=lambda code: fake_steam("222222"))
    assert not wrong.verified


def test_proposal_preserves_original_version_patch_and_extension():
    assert proposed_filename("Game [v1.2] [한글패치].7z", "dlsite", "RJ123456") == (
        "Game [v1.2] [한글패치] [RJ123456].7z")
    assert proposed_filename("Game [v1.2].zip", "steam", "1091500") == (
        "Game [v1.2] [Steam 1091500].zip")
    assert proposed_filename("Game [RJ123456].zip", "dlsite", "RJ123456") == (
        "Game [RJ123456].zip")


def test_safe_rename_writes_journal_then_restores(tmp_path):
    original = tmp_path / "Game [v1.2].zip"
    original.write_bytes(b"archived bytes do not change")
    journal = tmp_path / "private" / "rename-history.jsonl"
    dest, message = safe_rename(
        original, proposed_filename(original.name, "dlsite", "RJ123456"),
        journal)
    assert dest.is_file()
    assert not original.exists()
    assert dest.read_bytes() == b"archived bytes do not change"
    assert "완료" in message
    after, before = undo_last(journal)
    assert after == dest and before == original
    assert original.read_bytes() == b"archived bytes do not change"
    assert not dest.exists()
    with pytest.raises(ValueError):
        undo_last(journal)


def test_collision_never_overwrites_other_archives(tmp_path):
    a = tmp_path / "Game.zip"
    b = tmp_path / "Game [RJ123456].zip"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    with pytest.raises(FileExistsError):
        safe_rename(a, b.name, tmp_path / "log.jsonl")
    assert a.read_bytes() == b"A" and b.read_bytes() == b"B"


@pytest.mark.parametrize("bad", [
    "../Evil.zip", "Game.exe", "CON.zip", "Game?.zip",
    "bad/name.zip", "name with newline\n.zip", "Name.zip ",
])
def test_unsafe_target_name_refused(tmp_path, bad):
    src = tmp_path / "Original.zip"
    src.write_bytes(b"keep")
    with pytest.raises(ValueError):
        safe_rename(src, bad, tmp_path / "log")
    assert src.read_bytes() == b"keep"


def test_undo_refuses_collision(tmp_path):
    src = tmp_path / "Game.zip"
    src.write_bytes(b"original")
    target, _ = safe_rename(src, "Game [RJ123456].zip",
                            tmp_path / "rename-log.jsonl")
    src.write_bytes(b"new user file")
    with pytest.raises(FileExistsError):
        undo_last(tmp_path / "rename-log.jsonl")
    assert src.read_bytes() == b"new user file"
    assert target.read_bytes() == b"original"


def test_history_survives_separate_rename_and_undo(tmp_path):
    a, b = tmp_path / "a.zip", tmp_path / "b.7z"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    journal = tmp_path / "j.jsonl"
    a2, _ = safe_rename(a, "a [RJ123456].zip", journal)
    b2, _ = safe_rename(b, "b [Steam 1091500].7z", journal)
    assert undo_last(journal) == (b2, b)
    assert undo_last(journal) == (a2, a)


def test_no_auto_rename_in_review_ui_module():
    source = (Path(__file__).resolve().parents[1] / "scripts" /
              "research_review_window.py").read_text(encoding="utf-8")
    assert "askyesno" in source
    assert "safe_rename" in source
    assert "self.verifications" in source
