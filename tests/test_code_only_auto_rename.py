"""Offline regression tests for opt-in bare-ID name changes and safe UNDO."""
from pathlib import Path

import pytest

from experiments.dlsite_detector.code_only import Result, Work
from experiments.dlsite_detector.code_only_renamer import (
    apply_code_only_renames, bare_id, history_dir, official_filename,
    plan_code_only_renames, undo_last_auto_rename,
)
from experiments.dlsite_detector.scan_handoff import ScanReport, RESULTS_DIR
from scripts import scan_then_prompt


def dl_work(code="RJ123456", title="정식 게임 이름", verified=True):
    return Work(code, title if verified else "", "maniax",
                f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html"
                if verified else "", "verified" if verified else "unavailable", "dlsite")


def steam_work(code="1091500", title="Steam Game", verified=True):
    return Work(code, title if verified else "", "game",
                f"https://store.steampowered.com/app/{code}/" if verified else "",
                "verified" if verified else "unavailable", "steam")


def row(filename, work=None, *, status="confirmed", store="dlsite"):
    return Result(filename, "archive", status, (work or dl_work(),),
                  selected_store=store)


@pytest.mark.parametrize(("filename","expected"), [
    ("RJ123456.zip", ("dlsite", "RJ123456")),
    ("[RJ123456].7z", ("dlsite", "RJ123456")),
    ("(RJ123456).zip", None),
    ("RJ123456 [v1.2].zip", None),
    ("[RJ123456.zip", None),
    ("RJ123456].zip", None),
    ("[Steam 1091500].rar", ("steam", "1091500")),
    ("Steam 1091500.zip", ("steam", "1091500")),
    ("1091500.zip", None),
    ("Game [RJ123456].zip", None),
    ("RJ123456.exe", None),
])
def test_bare_id_strict(filename, expected):
    assert bare_id(filename) == expected


def test_official_name_sanitizes_windows_invalid_chars():
    out = official_filename("Story: One / Part <3>", "dlsite", "RJ123456", ".7z")
    assert out == "Story One Part 3 [RJ123456].7z"
    assert official_filename("CON", "dlsite", "RJ123456", ".zip") is None
    assert official_filename("  ", "dlsite", "RJ123456", ".zip") is None


def test_rename_verified_dlsite_and_undo_preserves_archive_bytes(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    path = root / "RJ123456.zip"
    data = b"Fake game archive contents -- NEVER EXTRACTED"
    path.write_bytes(data)
    hist = tmp_path / "history"
    assert len(plan_code_only_renames(root, (row(path.name),))) == 1
    changed, _ = apply_code_only_renames(root, (row(path.name),),
                                         journal_directory=hist)
    target = root / "정식 게임 이름 [RJ123456].zip"
    assert changed == 1 and target.read_bytes() == data
    assert not path.exists()
    assert len(list(hist.glob("*.json"))) == 1
    restored, _ = undo_last_auto_rename(root, journal_directory=hist)
    assert restored == 1 and path.read_bytes() == data
    assert not target.exists()
    assert undo_last_auto_rename(root, journal_directory=hist)[0] == 0


def test_steam_app_id_rename(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    file = root / "[Steam 1091500].rar"
    file.write_bytes(b"fake")
    changed, _ = apply_code_only_renames(
        root, (row(file.name, steam_work(), store="steam"),),
        journal_directory=tmp_path / "journals")
    assert changed == 1
    assert (root / "Steam Game [Steam 1091500].rar").read_bytes() == b"fake"


def test_partial_and_unverified_entries_never_rename(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    (root / "RJ123456.zip").write_bytes(b"original")
    assert not plan_code_only_renames(root, (row("RJ123456.zip", status="partial"),))
    assert not plan_code_only_renames(
        root, (row("RJ123456.zip", dl_work(verified=False), status="excluded", store=""),))
    assert not plan_code_only_renames(
        root, (row("RJ123456.zip", steam_work(), store="steam"),))


def test_existing_game_title_unchanged_and_no_journal(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    name = "My Game [RJ123456].zip"
    (root / name).write_bytes(b"old")
    hist = tmp_path / "history"
    changed, _ = apply_code_only_renames(root, (row(name),), journal_directory=hist)
    assert changed == 0 and not hist.exists()
    assert (root / name).read_bytes() == b"old"


def test_windows_casefold_collision_is_blocked(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    (root / "RJ123456.zip").write_bytes(b"old")
    (root / "정식 게임 이름 [RJ123456].ZIP").write_bytes(b"other")
    assert plan_code_only_renames(root, (row("RJ123456.zip"),)) == []


def test_duplicate_filename_in_subfolders_is_blocked(tmp_path):
    root = tmp_path / "games"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    for side in ("a", "b"):
        (root / side / "RJ123456.zip").write_bytes(b"old")
    assert not plan_code_only_renames(root, (
        row("RJ123456.zip"), row("RJ123456.zip")))
    assert not plan_code_only_renames(root, (row("RJ123456.zip"),))


def test_undo_rejects_replaced_file_even_same_filename(tmp_path):
    root = tmp_path / "games"
    root.mkdir()
    source = root / "RJ123456.zip"
    source.write_bytes(b"original123456")
    hist = tmp_path / "history"
    assert apply_code_only_renames(root, (row(source.name),),
                                   journal_directory=hist)[0] == 1
    new = root / "정식 게임 이름 [RJ123456].zip"
    new.unlink()
    new.write_bytes(b"replacement")
    restored, warnings = undo_last_auto_rename(root, journal_directory=hist)
    assert restored == 0
    assert new.exists() and not source.exists()
    assert any("보호" in text for text in warnings)


def test_opt_in_option_2_start_before_folder_and_no_second_yes(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    source = root / "RJ123456.zip"
    source.write_bytes(b"keep bytes")
    monkeypatch.setenv("PLAYDOCK_AUTO_RENAME_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("PLAYDOCK_OFFICIAL_CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))
    scan = ScanReport((row(source.name),), 1)
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **k: scan)
    answers = iter(["2", str(root), "Y", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert scan_then_prompt.main([]) == 0
    assert not source.exists()
    assert (root / "정식 게임 이름 [RJ123456].zip").read_bytes() == b"keep bytes"
    result_dirs = list((root / RESULTS_DIR).iterdir())
    assert len(result_dirs) == 1
    assert [p.name for p in result_dirs[0].iterdir()] == [
        "PlayDock_Complete_Scan_And_AI_Prompt.txt"]


def test_opt_in_option_2_cancel_does_not_scan_or_rename(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    (root / "RJ123456.zip").write_bytes(b"old")
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("Never scan before Y")))
    answers = iter(["2", str(root), "N"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert scan_then_prompt.main([]) == 0
    assert (root / "RJ123456.zip").read_bytes() == b"old"
    assert not (root / RESULTS_DIR).exists()


def test_menu_3_undo_does_not_scan(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    old = root / "RJ123456.zip"
    old.write_bytes(b"data")
    history = tmp_path / "history"
    monkeypatch.setenv("PLAYDOCK_AUTO_RENAME_HISTORY_DIR", str(history))
    assert apply_code_only_renames(root, (row(old.name),),
                                   journal_directory=history)[0] == 1
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("UNDO must not scan")))
    answers = iter(["3", str(root), "Y", "UNDO", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert scan_then_prompt.main([]) == 0
    assert old.read_bytes() == b"data"
    assert not (root / RESULTS_DIR).exists()


def test_menu_3_requires_exact_undo(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    old = root / "RJ123456.zip"
    old.write_bytes(b"data")
    history = tmp_path / "history"
    monkeypatch.setenv("PLAYDOCK_AUTO_RENAME_HISTORY_DIR", str(history))
    assert apply_code_only_renames(root, (row(old.name),),
                                   journal_directory=history)[0] == 1
    answers = iter(["3", str(root), "Y", "undo", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert scan_then_prompt.main([]) == 0
    assert not old.exists()
    assert (root / "정식 게임 이름 [RJ123456].zip").exists()


def test_rename_mode_default_off_even_with_existing_bare_id(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    old = root / "RJ123456.zip"
    old.write_bytes(b"data")
    monkeypatch.setenv("PLAYDOCK_OFFICIAL_CATALOG_PATH", str(tmp_path / "catalog.sqlite3"))
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **k:
                        ScanReport((row(old.name),), 1))
    assert scan_then_prompt.run(root, output_dir=tmp_path / "out") == 0
    assert old.read_bytes() == b"data"
    assert not (root / "정식 게임 이름 [RJ123456].zip").exists()


def test_exe_offline_self_test_entrypoint(capsys):
    assert scan_then_prompt.main(["--self-test-renames"]) == 0
    assert "PASS" in capsys.readouterr().out
