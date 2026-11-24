from pathlib import Path
import json
import zipfile
from types import SimpleNamespace

import pytest

from core import Library
from game_collections import CollectionStore
from data_management import inventory, backup_data, inspect_backup, restore_data


def _build_sample(tmp_path):
    store = tmp_path / 'data'
    store.mkdir()
    archive = tmp_path / 'archives'
    installed = tmp_path / 'installed'
    archive.mkdir()
    installed.mkdir()
    (archive / 'Example.zip').write_bytes(b'dummy archive unchanged')
    library = Library(store)
    library.settings.update({'library': str(installed), 'archives': str(archive), 'first_run_complete': True})
    library.save_settings()
    games = library.scan()
    assert len(games) == 1
    game = games[0]
    library.update_meta(game, title='게임 이름', executable='Example.exe')
    art = library.art_dir(game)
    (art / 'icon.png').write_bytes(b'image not touched')
    cols = CollectionStore(store)
    cid = cols.create('RPG')
    cols.set_game_memberships(game.id, {cid})
    (store / 'product_titles.json').write_text('{"RJ1":{"title":"테스트"}}', encoding='utf-8')
    return library, games, cols, cid, archive


def test_inventory_includes_collections_and_saved_meta(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    view = inventory(library, games, cols)
    assert (view.games, view.archives, view.installed) == (1, 1, 0)
    assert (view.collections, view.collection_memberships, view.missing_memberships) == (1, 1, 0)
    assert (view.metadata, view.images, view.product_titles) == (1, 1, 1)
    assert view.image_bytes == len(b'image not touched')
    cols.set_game_memberships('not-available', {cid})
    view = inventory(library, games, cols)
    assert view.missing_memberships == 1
    assert view.collection_memberships == 2


def test_backup_restore_covers_settings_collections_and_art(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    zfile = tmp_path / 'my-data.zip'
    count = backup_data(library.store, games, zfile)
    assert count >= 5
    assert 'collections.json' in inspect_backup(zfile)
    with zipfile.ZipFile(zfile) as z:
        assert json.loads(z.read('manifest.json'))['format'] == 'PlayDockDataBackup'
        snapshot = json.loads(z.read('library_snapshot.json'))
        assert snapshot[0]['name'] == 'Example'
        assert not any('Example.zip' in n for n in z.namelist())
    cols.rename(cid, '변경한 모음집')
    library.update_meta(games[0], title='잘못된 이름')
    (library.art_dir(games[0]) / 'icon.png').write_bytes(b'another image')
    n, safety = restore_data(library.store, zfile)
    assert n == count
    assert safety.is_file()
    assert CollectionStore(library.store).list()[0]['name'] == 'RPG'
    assert library.title(games[0]) == '게임 이름'
    assert (library.art_dir(games[0]) / 'icon.png').read_bytes() == b'image not touched'
    assert (archive / 'Example.zip').read_bytes() == b'dummy archive unchanged'
    assert 'collections.json' in inspect_backup(safety)


def test_reject_unknown_and_traversal_paths(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    bad = tmp_path / 'bad.zip'
    def malicious(name):
        with zipfile.ZipFile(bad, 'w') as z:
            z.writestr('manifest.json', json.dumps({'format':'LocalGameShelfDataBackup','version':1,'files':[name]}))
            z.writestr(name, b'payload')
        with pytest.raises(ValueError):
            restore_data(library.store, bad)
    malicious('../collections.json')
    malicious('cache/../../settings.json')
    malicious('other.json')
    assert not (tmp_path / 'collections.json').exists()
    assert not (library.store / 'backups').exists()


def test_corrupt_backup_preserves_existing_data(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    bad = tmp_path / 'invalid.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('manifest.json', json.dumps({'format':'LocalGameShelfDataBackup','version':1,'files':['collections.json']}))
        z.writestr('collections.json', b'not a json')
    with pytest.raises(ValueError):
        restore_data(library.store, bad)
    assert CollectionStore(library.store).list()[0]['name'] == 'RPG'


def test_backup_does_not_follow_symlinks(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    folder = library.cache / ('f' * 22)
    try:
        folder.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('이 Windows 환경에서는 심볼릭 링크 생성 권한이 없습니다.')
    assert not any(str(folder) in name for name, _ in __import__('data_management')._data_paths(library.store))
    zfile = tmp_path / 'safe.zip'
    backup_data(library.store, games, zfile)
    assert not any(n.startswith('cache/ffffffffffffff') for n in inspect_backup(zfile))


def test_backup_has_no_program_install_or_game_binaries(tmp_path):
    library, games, cols, cid, archive = _build_sample(tmp_path)
    unrelated = library.store / 'some-game.exe'
    unrelated.write_bytes(b'exe')
    zfile = tmp_path / 'data.zip'
    backup_data(library.store, games, zfile)
    with zipfile.ZipFile(zfile) as z:
        assert 'some-game.exe' not in z.namelist()
        assert 'collections.json' in z.namelist()
