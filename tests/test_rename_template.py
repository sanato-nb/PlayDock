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
    peek = _run(script, "Preview", games, env=env)
    assert peek.returncode == 0, peek.stderr + peek.stdout
    assert before.exists() and not after.exists()
    applied = _run(script, "Apply", games, stdin="YES\n", env=env)
    assert applied.returncode == 0, applied.stderr + applied.stdout
    assert after.read_bytes() == b"original data must remain unchanged"
    assert not before.exists()
    history = list((tmp_path / "history").glob("*.json"))
    assert len(history) == 1
    restored = _run(script, "Undo", games, stdin="UNDO\n", env=env)
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
    attempt = _run(script, "Apply", games, stdin="YES\n",
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
    result = _run(script, "Apply", games, stdin="YES\n",
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
    peek = _run(script, "Preview", games)
    assert peek.returncode == 0, peek.stderr + peek.stdout
    assert a.exists() and not b.exists()
