"""Independent verifier for AI-filled PlayDock PowerShell rename plans."""
import json
from pathlib import Path
import pytest

from experiments.dlsite_detector.rename_template import PS1_TEMPLATE
from experiments.dlsite_detector.rename_validation import verify_rename_script
from scripts.scan_then_prompt import main


def filled(rules):
    data = json.dumps(rules, ensure_ascii=False)
    return PS1_TEMPLATE.replace("$renameJson = @'\n[]\n'@",
                                "$renameJson = @'\n" + data + "\n'@")


def test_original_script_verifies_without_changes():
    result = verify_rename_script(PS1_TEMPLATE, from_text=True)
    assert result.number_of_rules == 0


def test_ai_filled_json_verified_and_original_names_preserved():
    rules = [
        {"OldName": "한글판 [v1.2].zip", "NewName": "한글판 [v1.2] [RJ123456].zip"},
        {"OldName": "Hero's Quest.7z", "NewName": "Hero's Quest [Steam 1091500].7z"},
    ]
    result = verify_rename_script(filled(rules), from_text=True)
    assert result.number_of_rules == 2
    assert result.rules[0][0] == rules[0]["OldName"]


def test_modified_template_is_rejected_even_with_modified_hash():
    text = filled([{"OldName": "Game.zip", "NewName": "Game [RJ123456].zip"}])
    text = text.replace("Select-GameFolder", "Select-TamperedFolder")
    with pytest.raises(ValueError, match="기본 PS1 코드"):
        verify_rename_script(text, from_text=True)


def test_invalid_json_and_bad_filename_blocked():
    bad = PS1_TEMPLATE.replace("$renameJson = @'\n[]\n'@",
                               "$renameJson = @'\nnot-json\n'@")
    with pytest.raises(ValueError):
        verify_rename_script(bad, from_text=True)
    for rule in (
        {"OldName": "../bad.zip", "NewName": "good.zip"},
        {"OldName": "CON.zip", "NewName": "good.zip"},
        {"OldName": "bad.zip", "NewName": "good.exe"},
        {"OldName": "bad.zip", "NewName": "bad.zip"},
        {"OldName": "bad.zip", "NewName": "good.7z"},
    ):
        with pytest.raises(ValueError):
            verify_rename_script(filled([rule]), from_text=True)


def test_duplicate_old_or_new_names_blocked():
    a = {"OldName": "Game.zip", "NewName": "Game [RJ123456].zip"}
    b = {"OldName": "game.ZIP", "NewName": "Other.zip"}
    c = {"OldName": "Other.zip", "NewName": "game [rj123456].ZIP"}
    for rules in ([a, b], [a, c]):
        with pytest.raises(ValueError, match="중복"):
            verify_rename_script(filled(rules), from_text=True)


def test_verifier_handles_bom_and_crlf(tmp_path):
    ps1 = tmp_path / "rename_games.ps1"
    ps1.write_bytes(b"\xef\xbb\xbf" + filled(
        [{"OldName": "Game.zip", "NewName": "Game [RJ123456].zip"}]
    ).replace("\n", "\r\n").encode("utf-8"))
    assert verify_rename_script(ps1).number_of_rules == 1
    assert main(["--verify-rename-script", str(ps1)]) == 0


def test_verifier_cli_rejects_changed_engine(tmp_path):
    ps1 = tmp_path / "rename_games.ps1"
    ps1.write_text(PS1_TEMPLATE.replace("Undo-Last", "Undo-Broken"), encoding="utf-8-sig")
    assert main(["--verify-rename-script", str(ps1)]) == 1


def test_ai_has_no_permission_to_modify_code_beyond_json():
    text = PS1_TEMPLATE + "\nWrite-Host 'surprise'\n"
    with pytest.raises(ValueError):
        verify_rename_script(text, from_text=True)
