from refactor_test_support import launcher_source, editor_source

from pathlib import Path
_ui_main = launcher_source()

from io import BytesIO
import json
import stat
import sys
import types
import zipfile

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import (Library, install, archive_requires_password, uninstall_target,
                  ArchivePasswordRequired, Game, _unpack_rar)
from data_management import backup_data, inspect_backup
from models.library_tree import make_sidebar_groups
from services.launch_options import parse_game_arguments
from artwork import discover_local


def library(tmp_path):
    root, archives = tmp_path / 'installed', tmp_path / 'archives'
    root.mkdir()
    archives.mkdir()
    lib = Library(tmp_path / 'app_data')
    lib.change_root(root)
    lib.change_archive_root(archives)
    return lib


def zip_game(path, members):
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in members.items():
            z.writestr(name, content)


def test_manual_external_game_and_uninstall_guard(tmp_path):
    lib = library(tmp_path)
    ext = tmp_path / 'outside' / 'External Game'
    ext.mkdir(parents=True)
    exe = ext / 'main.exe'
    exe.write_bytes(b'MZ')
    game = lib.add_manual_executable(exe)
    actual = next(g for g in lib.scan() if g.external)
    assert actual.id == game.id
    assert actual.installed and actual.folder == ext
    assert lib.meta(actual)['executable'] == 'main.exe'
    assert lib.kind(actual) == '게임'
    with pytest.raises(ValueError, match='수동 등록'):
        uninstall_target(actual, lib.archive_root)
    with pytest.raises(ValueError, match='이미'):
        lib.add_manual_executable(exe)
    assert lib.remove_manual_executable(actual)
    assert not any(g.external for g in lib.scan())
    assert exe.exists()


def test_manual_games_participate_in_data_backup(tmp_path):
    lib = library(tmp_path)
    ext = tmp_path / 'external'
    ext.mkdir()
    exe = ext / 'run.exe'
    exe.write_bytes(b'MZ')
    lib.add_manual_executable(exe)
    backup = tmp_path / 'backup.zip'
    backup_data(lib.store, lib.scan(), backup)
    names = inspect_backup(backup)
    assert 'manual_games.json' in names


def test_manual_registration_in_existing_scanned_folder_is_rejected(tmp_path):
    lib = library(tmp_path)
    folder = lib.root / 'Already'
    folder.mkdir()
    exe = folder / 'game.exe'
    exe.write_bytes(b'MZ')
    with pytest.raises(ValueError, match='자동 인식'):
        lib.add_manual_executable(exe)


def test_all_files_are_games_even_if_name_mentions_patch(tmp_path):
    lib = library(tmp_path)
    zip_game(lib.archive_root / 'NOR [한글패치].zip', {'note.txt': b'abc'})
    zip_game(lib.archive_root / 'PASEC [v2.2].zip', {'PASEC.exe': b'MZ'})
    games = lib.scan()
    assert all(lib.kind(game) == '게임' for game in games)
    # Old versions may have stored a custom category: don't delete that data,
    # but also don't use it to classify anything in the library.
    patch = next(g for g in games if g.name.startswith('NOR'))
    lib.update_meta(patch, category='자료')
    assert lib.kind(patch) == '게임'


def test_sidebar_filters_and_sorting(tmp_path):
    lib = library(tmp_path)
    for name in ('AAA [한글패치].zip', 'BGame.zip', 'CGame.zip'):
        zip_game(lib.archive_root / name, {'readme.txt': b'abc'})
    games = lib.scan()
    rows = make_sidebar_groups(games, [], lib.title, filter_mode='all')
    assert len([g for row in rows for g in row.games]) == 3
    with pytest.raises(ValueError, match='필터'):
        make_sidebar_groups(games, [], lib.title, filter_mode='auxiliary')
    rows = make_sidebar_groups(games, [], lib.title, sort_mode='name_desc')
    assert [g.name for row in rows for g in row.games][0] == 'CGame'
    rows = make_sidebar_groups(games, [], lib.title, search='cgame')
    assert [g.name for row in rows for g in row.games] == ['CGame']


def test_rar_is_recognized_by_scan(tmp_path):
    lib = library(tmp_path)
    (lib.archive_root / 'Demo.rar').write_bytes(b'Rar!')
    game = lib.scan()[0]
    assert game.archive.suffix == '.rar' and not game.installed


def test_rar_safe_streaming_with_fake_backend(tmp_path, monkeypatch):
    class Info:
        filename = 'Game/main.exe'
        file_size = 2
        mode = 0
        file_redir = None
        def isdir(self): return False
        def is_symlink(self): return False
    class FakeRar:
        def __init__(self, path): self.path = path
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def needs_password(self): return False
        def infolist(self): return [Info()]
        def open(self, item, pwd=None): return BytesIO(b'MZ')
    monkeypatch.setitem(sys.modules, 'rarfile', types.SimpleNamespace(RarFile=FakeRar, tool_setup=lambda: None))
    stage = tmp_path / 'stage'
    stage.mkdir()
    _unpack_rar(tmp_path / 'fake.rar', stage, lambda n: None)
    assert (stage / 'Game' / 'main.exe').read_bytes() == b'MZ'
    assert not archive_requires_password(tmp_path / 'fake.rar')


def test_rar_rejects_traversal_before_extraction(tmp_path, monkeypatch):
    class Info:
        filename = '../escape.exe'
        file_size = 2
        mode = 0
        file_redir = None
        def isdir(self): return False
        def is_symlink(self): return False
    class FakeRar:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def needs_password(self): return False
        def infolist(self): return [Info()]
        def open(self, *args, **kwargs): raise AssertionError('unsafe extraction called')
    monkeypatch.setitem(sys.modules, 'rarfile', types.SimpleNamespace(RarFile=FakeRar, tool_setup=lambda: None))
    stage = tmp_path / 'stage'
    stage.mkdir()
    with pytest.raises(ValueError, match='상위 폴더'):
        _unpack_rar(tmp_path / 'fake.rar', stage, lambda n: None)
    assert not (tmp_path / 'escape.exe').exists()


def test_launch_arguments_parse(tmp_path):
    assert parse_game_arguments('--fullscreen --language ko') == ['--fullscreen', '--language', 'ko']
    assert parse_game_arguments('--path "C:\\Saved Games\\Mine"') == ['--path', 'C:\\Saved Games\\Mine']
    assert parse_game_arguments('') == []
    with pytest.raises(ValueError):
        parse_game_arguments('anything\nmore')


def _png(width, height):
    img = Image.new('RGB', (width, height), (47, 88, 123))
    data = BytesIO()
    img.save(data, format='PNG')
    return data.getvalue()


def test_image_discovery_from_unencrypted_zip_and_no_override(tmp_path, monkeypatch):
    lib = library(tmp_path)
    filename = lib.archive_root / 'Game Alpha.zip'
    zip_game(filename, {'Game Alpha/Banner.PNG': _png(1200, 450), 'Game Alpha/icon.png': _png(180, 180)})
    game = lib.scan()[0]
    found = discover_local(lib, game)
    assert set(found) == {'hero', 'icon'}
    hero = lib.art_dir(game) / 'hero.png'
    assert hero.is_file()

    def unexpected_scan(*args):
        pytest.fail("Cached artwork should prevent another candidate scan")

    with monkeypatch.context() as cached:
        cached.setattr("artwork._archive_artwork_candidates", unexpected_scan)
        cached.setattr("artwork._find_artwork_library", unexpected_scan)
        assert discover_local(lib, game) == []
    with Image.open(hero) as img:
        assert img.size == (1600, 520)

    icon = hero.with_name("icon.png")
    icon.unlink()
    assert discover_local(lib, game) == ["icon"]
    assert icon.is_file()


def test_explicit_local_images_prioritized(tmp_path):
    lib = library(tmp_path)
    zip_game(lib.archive_root / 'Game Alpha.zip', {'README.txt': b'hi'})
    game = lib.scan()[0]
    art = lib.store / 'artwork_library' / 'Game Alpha'
    art.mkdir(parents=True)
    (art / 'banner.jpg').write_bytes(_png(1200, 500))
    assert discover_local(lib, game) == ['hero']


def test_manual_game_id_and_metadata_survive_installed_root_change(tmp_path):
    lib = library(tmp_path)
    outside = tmp_path / 'elsewhere'
    outside.mkdir()
    exe = outside / 'start.exe'
    exe.write_bytes(b'MZ')
    game = lib.add_manual_executable(exe)
    original_id = game.id
    lib.update_meta(game, title='A special title')
    new_root = tmp_path / 'another_library'
    new_root.mkdir()
    lib.change_root(new_root)
    selected = next(g for g in lib.scan() if g.external)
    assert selected.id == original_id
    assert lib.title(selected) == 'A special title'


def test_upgrade_ui_wiring():
    app_source = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
    for feature in ('register_manual_game', 'open_sort_menu',
                    'edit_launch_options',
                    'refresh_local_art', 'open_artwork_library'):
        assert f'def {feature}(' in app_source
    assert 'QProcess.startDetached(str(exe), arguments' in app_source
    assert 'if game is not None and game.installed and not game.external:' in app_source
