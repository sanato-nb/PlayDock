from refactor_test_support import launcher_source, editor_source
"""Uninstall safety tests; never touch the real OS trash in automated tests."""
from pathlib import Path
_ui_main = launcher_source()


import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Game, Library, uninstall_target, uninstall_to_recycle_bin


def make_library(tmp_path, *, archive=True):
    store = tmp_path / 'config'
    root = tmp_path / 'installed'
    archives = tmp_path / 'archives'
    root.mkdir()
    archives.mkdir()
    lib = Library(store)
    lib.change_root(root)
    lib.change_archive_root(archives)
    original = archives / 'PASEC.zip'
    if archive:
        with zipfile.ZipFile(original, 'w') as zf:
            zf.writestr('Game.exe', b'MZ')
    game_dir = root / 'PASEC'
    game_dir.mkdir()
    (game_dir / 'Game.exe').write_bytes(b'MZ')
    game = lib.scan()[0]
    return lib, game, game_dir, original


def test_uninstall_moves_folder_only_and_preserves_archive_and_metadata(tmp_path):
    lib, game, folder, archive = make_library(tmp_path)
    game_id = game.id
    lib.update_meta(game, title='Better Game Name', artwork_source='user',
                    launch_confirmed_executable='game.exe', executable='Game.exe')
    art = lib.art_dir(game) / 'icon.png'
    art.write_bytes(b'png-example')
    calls = []
    dest = tmp_path / 'mock_recycle_bin' / 'PASEC'
    dest.parent.mkdir()

    def move(source):
        calls.append(Path(source))
        Path(source).rename(dest)

    removed = uninstall_to_recycle_bin(game, lib.archive_root, move_to_trash=move)
    assert removed == folder
    assert calls == [folder]
    assert not folder.exists()
    assert (dest / 'Game.exe').exists()
    assert archive.exists(), 'Never touch the original ZIP/7z'
    rescanned = lib.scan()
    assert len(rescanned) == 1
    assert not rescanned[0].installed
    assert rescanned[0].id == game_id
    assert lib.title(rescanned[0]) == 'Better Game Name'
    assert art.read_bytes() == b'png-example'


def test_folder_only_game_disappears_after_uninstall(tmp_path):
    lib, game, folder, _ = make_library(tmp_path, archive=False)
    target = tmp_path / 'mock_trash'
    uninstall_to_recycle_bin(game, lib.archive_root, lambda src: Path(src).rename(target))
    assert lib.scan() == []
    assert (target / 'Game.exe').exists()


def test_uninstall_rejects_library_root(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    game.folder = lib.root
    with pytest.raises(ValueError, match='바로 아래'):
        uninstall_target(game, lib.archive_root)
    assert folder.exists()


def test_uninstall_rejects_nested_or_external_folder(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    nested = folder / 'subfolder'
    nested.mkdir()
    game.folder = nested
    with pytest.raises(ValueError, match='바로 아래'):
        uninstall_target(game, lib.archive_root)
    outside = tmp_path / 'other'
    outside.mkdir()
    game.folder = outside
    with pytest.raises(ValueError, match='바로 아래'):
        uninstall_target(game, lib.archive_root)


def test_uninstall_rejects_link_to_outside(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    link = lib.root / 'link'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Platform prohibits creating directory symlinks')
    game.folder = link
    with pytest.raises(ValueError, match='링크'):
        uninstall_target(game, lib.archive_root)
    assert outside.exists()


def test_uninstall_rejects_archive_storage_inside_game_folder(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    new_archive_root = folder / 'archives'
    new_archive_root.mkdir()
    with pytest.raises(ValueError, match='압축파일 보관 폴더'):
        uninstall_target(game, new_archive_root)


def test_uninstall_rejects_original_archive_inside_game_folder(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    game.archive = folder / 'game.zip'
    game.archive.write_bytes(b'x')
    with pytest.raises(ValueError, match='원본 압축파일'):
        uninstall_target(game, lib.archive_root)


def test_uninstall_rejects_folder_missing(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    game.folder = None
    with pytest.raises(FileNotFoundError):
        uninstall_target(game, lib.archive_root)


def test_trash_failure_does_not_delete_files(tmp_path):
    lib, game, folder, archive = make_library(tmp_path)

    def failing_mover(_):
        raise PermissionError('Game is running')

    with pytest.raises(PermissionError):
        uninstall_to_recycle_bin(game, lib.archive_root, failing_mover)
    assert folder.is_dir() and archive.is_file()


def test_invalid_target_does_not_invoke_trash(tmp_path):
    lib, game, folder, _ = make_library(tmp_path)
    game.folder = folder / 'Game.exe'
    calls = []
    with pytest.raises(FileNotFoundError):
        uninstall_to_recycle_bin(game, lib.archive_root, calls.append)
    assert calls == []


def test_ui_contains_discoverable_uninstall_actions():
    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
    assert "self.uninstall_btn = self.action_button(\"설치 제거\", self.uninstall_game)" in source
    assert "remove = menu.addAction('설치 제거 (휴지통으로 이동)')" in source
    assert "if game is not None and game.installed and not game.external:" in source
    assert 'self.uninstall_worker = UninstallThread(game, self.library.archive_root)' in source
    assert 'launch_confirmed_executable=None' in source


def test_noop_mover_does_not_report_success(tmp_path):
    lib, game, folder, archive = make_library(tmp_path)
    with pytest.raises(OSError, match='남아 있습니다'):
        uninstall_to_recycle_bin(game, lib.archive_root, lambda _src: None)
    assert folder.exists() and archive.exists()
