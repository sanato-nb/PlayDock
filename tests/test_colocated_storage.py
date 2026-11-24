"""Installed single-folder data, migration and uninstall protections."""
from pathlib import Path
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.local import (data_dir_for_executable, legacy_data_dir, marker_is_valid,
                           migrate_legacy_data, program_store, write_install_marker)
from install_management import normalize_program_path
from storage.setup_paths import save_folder_settings
from core import Library
from storage.collections import CollectionStore


def test_only_marked_frozen_app_uses_colocated_data(tmp_path, monkeypatch):
    program = tmp_path / 'LGS'
    program.mkdir()
    exe = program / 'PlayDock.exe'
    expected = legacy_data_dir() if legacy_data_dir().exists() else legacy_data_dir().with_name('PlayDock')
    assert data_dir_for_executable(exe, frozen=False) == expected
    assert data_dir_for_executable(exe, frozen=True) == expected
    write_install_marker(program)
    assert marker_is_valid(program)
    assert data_dir_for_executable(exe, frozen=True) == program / 'data'
    assert data_dir_for_executable(program / 'PlayDock_TitleEditor.exe', frozen=True) == program / 'data'


def test_migrates_legacy_json_and_game_art_without_changing_source(tmp_path):
    source = tmp_path / 'legacy'
    dest = tmp_path / 'LocalGameShelf' / 'data'
    id1 = 'a' * 22
    folder = source / 'cache' / id1
    folder.mkdir(parents=True)
    (source / 'settings.json').write_text('{"library":"C:/game","archives":"C:/archives"}',encoding='utf-8')
    (source / 'collections.json').write_text('{"collections":[{"id":"x","name":"RPG","game_ids":[]}]}',encoding='utf-8')
    (folder / 'meta.json').write_text('{"title":"Renamed"}', encoding='utf-8')
    (folder / 'hero.png').write_bytes(b'fakepng')
    (source / 'some_other_game.zip').write_bytes(b'do not copy')
    result = migrate_legacy_data(dest, [source])
    assert result['copied'] == 4
    assert (dest / 'collections.json').read_bytes() == (source / 'collections.json').read_bytes()
    assert (dest / 'cache' / id1 / 'meta.json').read_bytes() == (folder / 'meta.json').read_bytes()
    assert (source / 'collections.json').is_file()
    assert not (dest / 'some_other_game.zip').exists()
    # Re-running never overwrites destination changes.
    (dest / 'cache' / id1 / 'meta.json').write_text('updated by user')
    assert migrate_legacy_data(dest, [source])['copied'] == 0
    assert (dest / 'cache' / id1 / 'meta.json').read_text() == 'updated by user'


def test_legacy_migration_imported_by_game_library(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    (old / 'collections.json').write_text(json.dumps({'version':1,'collections':[{'id':'one','name':'RPG','game_ids':[]}]}), encoding='utf-8')
    folder = tmp_path / 'app' / 'data'
    migrate_legacy_data(folder,[old])
    save_folder_settings(str(tmp_path/'archives'),str(tmp_path/'installed'), store_path=folder/'settings.json')
    library = Library(store=folder)
    collections = CollectionStore(library.store)
    assert collections.list()[0]['name'] == 'RPG'
    assert library.archive_root == tmp_path / 'archives'
    assert library.root == tmp_path / 'installed'


def test_migrate_does_not_follow_symlink(tmp_path):
    src = tmp_path / 'legacy'; src.mkdir()
    (src / 'settings.json').write_text('{}')
    dest = tmp_path / 'app' / 'data'
    dest.mkdir(parents=True)
    outside = tmp_path / 'outside'; outside.mkdir()
    (dest / 'cache').symlink_to(outside, target_is_directory=True)
    id1 = 'a' * 22
    (src / 'cache' / id1).mkdir(parents=True)
    (src / 'cache' / id1 / 'icon.png').write_bytes(b'png')
    with pytest.raises(ValueError):
        migrate_legacy_data(dest,[src])
    assert not list(outside.iterdir())


def test_installer_rejects_game_directory_overlap(tmp_path):
    archives, games = tmp_path/'archives', tmp_path/'games'
    with pytest.raises(ValueError):
        normalize_program_path(games/'application', archives, games)
    with pytest.raises(ValueError):
        normalize_program_path(tmp_path, archives, games)
    assert normalize_program_path(tmp_path/'App', archives, games) == tmp_path/'App'


def test_uninstaller_preserves_data_in_same_program_folder(tmp_path, monkeypatch):
    import install_management as mgr
    folder = tmp_path/'LocalGameShelf'
    folder.mkdir()
    write_install_marker(folder)
    data = program_store(folder)
    (data/'cache').mkdir(parents=True)
    (data/'collections.json').write_text('keep')
    (data/'cache'/'icon.png').write_bytes(b'icon')
    for file in mgr.INSTALLED_FILES:
        (folder/file).write_bytes(b'MZ')
    monkeypatch.setattr(mgr,'app_install_directory',lambda:folder)
    monkeypatch.setattr(mgr,'expected_shortcuts',lambda:[])
    monkeypatch.setattr(mgr,'remove_uninstall_entry',lambda:None)
    mgr.uninstall_application()
    assert (data/'collections.json').read_text() == 'keep'
    assert (data/'cache'/'icon.png').read_bytes() == b'icon'
    assert not any((folder/file).exists() for file in mgr.INSTALLED_FILES)
