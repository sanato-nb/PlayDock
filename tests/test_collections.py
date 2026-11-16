from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_collections import CollectionStore
from core import Library, save_json
from test_core import new_library, write_zip


def test_create_and_reload(tmp_path):
    store = CollectionStore(tmp_path)
    cid = store.create('즐겨찾기')
    store.set_game_memberships('abc', {cid})
    assert CollectionStore(tmp_path).members(cid) == {'abc'}
    assert CollectionStore(tmp_path).list()[0]['name'] == '즐겨찾기'


def test_game_multiple_collections_and_unassign(tmp_path):
    cs = CollectionStore(tmp_path)
    a = cs.create('RPG')
    b = cs.create('완료')
    cs.set_game_memberships('game1', {a, b})
    cs.set_game_memberships('game2', {a})
    assert {c['name'] for c in cs.for_game('game1')} == {'RPG', '완료'}
    cs.set_game_memberships('game1', {b})
    assert cs.members(a) == {'game2'}
    assert cs.members(b) == {'game1'}


def test_rename_and_delete_doesnt_modify_games(tmp_path):
    lib, root = new_library(tmp_path)
    write_zip(lib.archive_root / 'GameA.zip', {'main.exe': b'MZ'})
    game = lib.scan()[0]
    cs = CollectionStore(lib.store)
    cid = cs.create('old')
    cs.set_game_memberships(game.id, {cid})
    cs.rename(cid, 'new')
    assert cs.for_game(game.id)[0]['name'] == 'new'
    cs.delete(cid)
    assert cs.for_game(game.id) == []
    assert (lib.archive_root / 'GameA.zip').exists()


def test_duplicate_and_invalid_names(tmp_path):
    cs = CollectionStore(tmp_path)
    cs.create('RPG')
    for name in ('rpg', '', '   ', '모든 게임', '설치됨', '미설치', 'x' * 81):
        with pytest.raises(ValueError):
            cs.create(name)
    cid = cs.create('기타')
    with pytest.raises(ValueError):
        cs.rename(cid, 'RPG')


def test_invalid_membership_rejected(tmp_path):
    cs = CollectionStore(tmp_path)
    with pytest.raises(ValueError):
        cs.set_game_memberships('abc', {'unknown'})


def test_does_not_clear_collection_when_game_missing(tmp_path):
    cs = CollectionStore(tmp_path)
    cid = cs.create('Wishlist')
    cs.set_game_memberships('missing_game', {cid})
    cs2 = CollectionStore(tmp_path)
    assert cs2.members(cid) == {'missing_game'}


def test_corrupted_data_is_ignored(tmp_path):
    save_json(tmp_path / 'collections.json', {'collections': [123, {'id': 'x', 'name': 'ok', 'game_ids': [5, 'g', 'g']}, {'id': 'bad', 'name': '', 'game_ids': []}]})
    cs = CollectionStore(tmp_path)
    assert cs.list() == [{'id': 'x', 'name': 'ok', 'game_ids': ['g']}]
