from pathlib import Path
import zipfile
import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Library, install, validate_archive_member, executable_candidates, game_key


def write_zip(path: Path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def new_library(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    lib = Library(tmp_path / "settings")
    lib.change_root(root)
    archives = tmp_path / "archives"
    archives.mkdir()
    lib.change_archive_root(archives)
    return lib, root


def test_archive_detect_and_install(tmp_path):
    lib, root = new_library(tmp_path)
    zpath = lib.archive_root / "My Game.zip"
    write_zip(zpath, {"My Game/Game.exe": b"MZ" + b"\0" * 100, "My Game/readme.txt": b"hello"})
    games = lib.scan()
    assert len(games) == 1
    assert not games[0].installed
    progress = []
    installed = install(games[0], progress.append)
    assert installed == root / "My Game"
    assert (installed / "Game.exe").read_bytes()[:2] == b"MZ"
    assert zpath.exists(), "Original archive should be preserved"
    assert progress[-1] == 100
    updated = lib.scan()
    assert len(updated) == 1 and updated[0].installed
    assert executable_candidates(installed)[0].name == "Game.exe"


def test_no_overwrite_existing_folder(tmp_path):
    lib, root = new_library(tmp_path)
    write_zip(lib.archive_root / "Abc.zip", {"main.exe": b"hi"})
    (root / "Abc").mkdir()
    with pytest.raises(FileExistsError):
        install(lib.scan()[0])


@pytest.mark.parametrize("name", ["../evil.exe", "a/../../evil.exe", "/etc/passwd", "C:\\temp\\oops", "\\\\server\\share\\hi"])
def test_traversal_rejected(name):
    with pytest.raises(ValueError):
        validate_archive_member(name)


def test_traversal_archive_does_not_escape(tmp_path):
    lib, root = new_library(tmp_path)
    write_zip(lib.archive_root / "Bad.zip", {"../hacked.txt": b"oops"})
    with pytest.raises(ValueError):
        install(lib.scan()[0])
    assert not (tmp_path / "hacked.txt").exists()
    assert not (root / "Bad").exists()


def test_exe_filters_installers(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    for name in ("setup.exe", "UnityCrashHandler64.exe", "CoolGame.exe", "uninstall.exe"):
        (game / name).write_bytes(b"MZ")
    candidates = executable_candidates(game, "CoolGame")
    assert [p.name for p in candidates] == ["CoolGame.exe"]


def test_game_meta_cache_persists(tmp_path):
    lib, root = new_library(tmp_path)
    write_zip(lib.archive_root / "RJ123 Title.zip", {"game.exe": b"MZ"})
    game = lib.scan()[0]
    lib.update_meta(game, title="Nice game")
    lib2 = Library(lib.store)
    assert lib2.title(lib2.scan()[0]) == "Nice game"
    assert (lib2.art_dir(game) / "meta.json").is_file()


def test_same_archive_and_folder_identified_as_one(tmp_path):
    lib, root = new_library(tmp_path)
    write_zip(lib.archive_root / "NAME.zip", {"game.exe": b"MZ"})
    (root / "name").mkdir()
    (root / "name" / "game.exe").write_bytes(b"MZ")
    assert len(lib.scan()) == 1
    assert lib.scan()[0].installed


def test_unrelated_folders_are_not_games(tmp_path):
    lib, root = new_library(tmp_path)
    (root / "file").mkdir()
    (root / "screenshots").mkdir()
    (root / "Working Game").mkdir()
    (root / "Working Game" / "CoolGame.exe").write_bytes(b"MZ")
    write_zip(lib.archive_root / "Archived Title.7z", {"placeholder.txt": b"archive"})
    assert [game.name for game in lib.scan()] == ["Archived Title", "Working Game"]


def test_relocating_archive_directory_keeps_game_cache(tmp_path):
    lib, root = new_library(tmp_path)
    old_zip = lib.archive_root / "PASEC.zip"
    write_zip(old_zip, {"Game.exe": b"MZ"})
    old_game = lib.scan()[0]
    lib.update_meta(old_game, title="PASEC Test")
    new_dir = tmp_path / "different_archives"
    new_dir.mkdir()
    old_zip.rename(new_dir / old_zip.name)
    lib.change_archive_root(new_dir)
    new_game = lib.scan()[0]
    assert new_game.id == old_game.id
    assert lib.title(new_game) == "PASEC Test"
    installed = install(new_game)
    assert installed.parent == root
    assert (new_dir / "PASEC.zip").is_file()


def test_settings_migration_from_v011(tmp_path):
    from core import save_json
    root = tmp_path / "old_mixed_game"
    root.mkdir()
    write_zip(root / "My Old Game.zip", {"game.exe": b"MZ"})
    store = tmp_path / "settings"
    save_json(store / "settings.json", {"library": str(root), "auto_art": False})
    lib = Library(store)
    assert lib.root == root
    assert lib.archive_root == root
    game = lib.scan()[0]
    assert game.archive == root / "My Old Game.zip"
    assert not game.installed


def test_configured_paths_persist_independently(tmp_path):
    lib, installed = new_library(tmp_path)
    archives = lib.archive_root
    new_installs = tmp_path / "new_installs"
    new_installs.mkdir()
    lib.change_root(new_installs)
    lib2 = Library(lib.store)
    assert lib2.archive_root == archives
    assert lib2.root == new_installs
