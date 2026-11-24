"""Static, no-API PowerShell renamer carried in the AI prompt.

Never run against real game archives. Windows tests use disposable dummy files.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from experiments.dlsite_detector.rename_template import PS1_TEMPLATE
from experiments.dlsite_detector.scan_handoff import ScanReport, render_combined_txt
from experiments.dlsite_detector.code_only import Result


def _filled(old, new):
    payload = json.dumps([{"OldName": old, "NewName": new}], ensure_ascii=False)
    assert "$renameJson = @'\n[]\n'@" in PS1_TEMPLATE
    return PS1_TEMPLATE.replace("$renameJson = @'\n[]\n'@",
                                "$renameJson = @'\n" + payload + "\n'@")


def _write_script(tmp_path, content):
    script = tmp_path / "rename_games.ps1"
    script.write_text(content, encoding="utf-8-sig")
    return script


def _run(script, mode, folder, *, stdin="", env=None):
    import os
    actual_env = os.environ.copy()
    if env:
        actual_env.update(env)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Mode", mode, "-Folder", str(folder)],
        input=stdin, text=True, capture_output=True, errors="replace",
        env=actual_env, timeout=35)


def test_no_dynamic_user_data_or_developer_identifiers_in_base_script():
    assert "github.com" not in PS1_TEMPLATE.casefold()
    assert "sanato" not in PS1_TEMPLATE.casefold()
    assert "C:\\Users" not in PS1_TEMPLATE
    assert "$renameJson = @'\n[]\n'@" in PS1_TEMPLATE
    assert "Select-GameFolder" in PS1_TEMPLATE
    assert "Get-ArchiveFiles" in PS1_TEMPLATE
    assert "Rename-Item" in PS1_TEMPLATE
    assert "Undo-Last" in PS1_TEMPLATE
    assert PS1_TEMPLATE.count("BEGIN AI RULES") == 1
    assert PS1_TEMPLATE.count("END AI RULES") == 1


def test_combined_txt_includes_a_single_copyable_ps1_block():
    report = ScanReport((Result("Unknown [v1].zip", "archive", "excluded"),), 1)
    output = render_combined_txt(report)
    fence = chr(96) * 3
    pattern = re.escape(fence) + r"powershell\n(.*?)\n" + re.escape(fence)
    match = re.search(pattern, output, flags=re.DOTALL)
    assert match
    assert match.group(1).strip() == PS1_TEMPLATE.strip()
    assert output.count(fence + "powershell") == 1
    assert output.count("Unknown [v1].zip") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_preview_apply_then_undo_in_nested_folder(tmp_path):
    games = tmp_path / "game dir"
    sub = games / "inner"
    sub.mkdir(parents=True)
    before = sub / "Test Game [v1.2].zip"
    after = sub / "Test Game [v1.2] [RJ123456].zip"
    before.write_bytes(b"original data must remain unchanged")
    script = _write_script(tmp_path, _filled(before.name, after.name))
    env = {"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "history")}
    peek = _run(script, "Preview", games, stdin="Y\n", env=env)
    assert peek.returncode == 0, peek.stderr + peek.stdout
    assert before.exists() and not after.exists()
    applied = _run(script, "Apply", games, stdin="Y\nYES\n", env=env)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert after.read_bytes() == b"original data must remain unchanged"
    assert not before.exists()
    history = list((tmp_path / "history").glob("*.json"))
    assert len(history) == 1
    restored = _run(script, "Undo", games, stdin="Y\nUNDO\n", env=env)
    assert restored.returncode == 0, restored.stderr + restored.stdout
    assert before.read_bytes() == b"original data must remain unchanged"
    assert not after.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_existing_target_blocks_mutation(tmp_path):
    games = tmp_path / "g"
    games.mkdir()
    a = games / "One.zip"
    b = games / "One [RJ123456].zip"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    script = _write_script(tmp_path, _filled(a.name, b.name))
    attempt = _run(script, "Apply", games, stdin="Y\nYES\n",
                   env={"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "log")})
    assert attempt.returncode != 0, attempt.stdout + attempt.stderr
    assert a.read_bytes() == b"A"
    assert b.read_bytes() == b"B"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_duplicate_basename_in_subfolders_is_rejected(tmp_path):
    games = tmp_path / "g"
    (games / "a").mkdir(parents=True)
    (games / "b").mkdir()
    for d in ("a", "b"):
        (games / d / "Duplicate.zip").write_bytes(d.encode())
    script = _write_script(tmp_path, _filled("Duplicate.zip", "Duplicate [RJ123456].zip"))
    result = _run(script, "Apply", games, stdin="Y\nYES\n",
                  env={"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "log")})
    assert result.returncode != 0, result.stderr + result.stdout
    assert all((games / d / "Duplicate.zip").exists() for d in ("a", "b"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_apostrophe_filename_is_safe_as_json_data(tmp_path):
    games = tmp_path / "g"
    games.mkdir()
    a = games / "Hero's Quest.7z"
    b = games / "Hero's Quest [RJ123456].7z"
    a.write_bytes(b"bits")
    script = _write_script(tmp_path, _filled(a.name, b.name))
    peek = _run(script, "Preview", games, stdin="Y\n")
    assert peek.returncode == 0, peek.stderr + peek.stdout
    assert a.exists() and not b.exists()



@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_selected_folder_requires_extra_yes_confirmation(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    original = games / "One.zip"
    original.write_bytes(b"untouched")
    script = _write_script(tmp_path, _filled("One.zip", "One [RJ123456].zip"))
    result = _run(script, "Apply", games, stdin="\nYES\n",
                  env={"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "history")})
    assert result.returncode == 0, result.stderr + result.stdout
    assert original.read_bytes() == b"untouched"
    assert not (games / "One [RJ123456].zip").exists()
    assert not (tmp_path / "history").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_altered_engine_self_checksum_fails_before_file_actions(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    original = games / "One.zip"
    original.write_bytes(b"untouched")
    code = _filled("One.zip", "One [RJ123456].zip")
    assert "선택한 폴더:" in code
    code = code.replace("선택한 폴더:", "변경된 폴더:", 1)
    script = _write_script(tmp_path, code)
    result = _run(script, "Apply", games, stdin="Y\nYES\n")
    assert result.returncode != 0, result.stderr + result.stdout
    assert original.read_bytes() == b"untouched"
    assert not (games / "One [RJ123456].zip").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_undo_rejects_modified_renamed_file(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    original = games / "One.zip"
    renamed = games / "One [RJ123456].zip"
    original.write_bytes(b"untouched")
    script = _write_script(tmp_path, _filled(original.name, renamed.name))
    env = {"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "history")}
    applied = _run(script, "Apply", games, stdin="Y\nYES\n", env=env)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert renamed.exists() and not original.exists()
    renamed.write_bytes(b"modified data now different length")
    undo = _run(script, "Undo", games, stdin="Y\nUNDO\n", env=env)
    assert renamed.exists() and not original.exists()
    assert b"modified" in renamed.read_bytes()
    journal = json.loads(next((tmp_path / "history").glob("*.json")).read_text(encoding="utf-8-sig"))
    assert journal["Undone"] is False
    assert journal["Records"][0]["State"] == "done"
    assert len(journal["Records"][0]["ContentSignature"]) == 64


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 required")
def test_undo_rejects_same_size_replaced_file(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    old = games / "One.zip"
    new = games / "One [RJ123456].zip"
    old.write_bytes(b"abcdef")
    script = _write_script(tmp_path, _filled(old.name, new.name))
    env = {"PLAYDOCK_RENAME_HISTORY_DIR": str(tmp_path / "history")}
    applied = _run(script, "Apply", games, stdin="Y\nYES\n", env=env)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert new.exists()
    original_stat = new.stat()
    # Replacing a file breaks its filesystem identity even with same size/time.
    new.unlink()
    new.write_bytes(b"123456")
    import os
    os.utime(new, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    undo = _run(script, "Undo", games, stdin="Y\nUNDO\n", env=env)
    assert new.read_bytes() == b"123456"
    assert not old.exists()
    journal = json.loads(next((tmp_path / "history").glob("*.json")).read_text(encoding="utf-8-sig"))
    assert journal["Undone"] is False
    assert journal["Records"][0]["State"] == "done"
    assert len(journal["Records"][0]["ContentSignature"]) == 64


def test_template_has_original_code_digest_and_file_identity():
    from experiments.dlsite_detector.rename_template import PS1_TEMPLATE_SHA256
    assert len(PS1_TEMPLATE_SHA256) == 64
    assert PS1_TEMPLATE_SHA256 in PS1_TEMPLATE
    assert "__PLAYDOCK_HASH__" not in PS1_TEMPLATE
    assert "Assert-TemplateIntegrity" in PS1_TEMPLATE
    assert "PlayDockFileId" in PS1_TEMPLATE
    assert "CreationUtcTicks" in PS1_TEMPLATE
    assert "LastWriteUtcTicks" in PS1_TEMPLATE
    assert "Get-ArchiveSignature" in PS1_TEMPLATE
    assert "ContentSignature" in PS1_TEMPLATE
    assert "이 폴더가 맞습니까?" in PS1_TEMPLATE
