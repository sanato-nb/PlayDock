"""Stage 7-G/I operation counts and unchanged results."""
from contextlib import contextmanager
from pathlib import Path

from core import Game, Library
from database.work_repository import WorkDatabase
from services import catalog_collection_service, library_service
from services.data_service import inventory
from storage.collections import CollectionStore


def test_catalog_entry_parses_filename_codes_once(tmp_path, monkeypatch):
    lib = Library(tmp_path / "data")
    game = Game("sample", "Sample", tmp_path,
                archive=tmp_path / "Sample [RJ123456].zip")
    original = catalog_collection_service.codes_in
    calls = []
    def counted(label):
        calls.append(label)
        return original(label)
    monkeypatch.setattr(catalog_collection_service, "codes_in", counted)
    [entry] = catalog_collection_service.game_catalog_entries(lib, [game])
    assert entry.explicit_code == "RJ123456"
    assert calls == [game.archive.name]


def test_verified_game_link_uses_one_connection(tmp_path, monkeypatch):
    db = WorkDatabase(tmp_path)
    db._upsert_verified([{"store": "dlsite", "code": "RJ123456",
                          "title": "Example",
                          "page_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}])
    original = db.connect
    calls = []
    @contextmanager
    def counted():
        calls.append(True)
        with original() as connection:
            yield connection
    monkeypatch.setattr(db, "connect", counted)
    assert db.save_verified_game_link("game", "dlsite", "rj123456")
    assert len(calls) == 1
    assert db.get_link("game") == ("dlsite", "RJ123456")
    calls.clear()
    assert not db.save_verified_game_link("other", "dlsite", "RJ999999")
    assert len(calls) == 1
    assert db.get_link("other") is None


def test_library_default_path_is_resolved_only_when_needed(tmp_path, monkeypatch):
    calls = []
    def default():
        calls.append(True)
        return tmp_path / "default"
    monkeypatch.setattr(library_service, "default_library", default)
    lib = Library(tmp_path / "data")
    assert len(calls) == 1
    lib.save_settings()
    calls.clear()
    again = Library(tmp_path / "data")
    assert again.settings == lib.settings
    assert calls == []


def test_inventory_preserves_membership_and_orphan_counts(tmp_path):
    library = Library(tmp_path / "data")
    game = Game("sample", "Sample", tmp_path)
    library.update_meta(game, title="Sample")
    orphan = library.cache / ("a" * 22)
    orphan.mkdir()
    (orphan / "meta.json").write_text("{}", encoding="utf-8")
    (orphan / "icon.png").write_bytes(b"image")
    collections = CollectionStore(library.store)
    a, b = collections.create("A"), collections.create("B")
    collections.set_game_memberships(game.id, {a, b})
    collections.set_game_memberships("missing", {a})
    result = inventory(library, [game], collections)
    assert (result.collection_memberships, result.missing_memberships) == (3, 1)
    assert (result.metadata, result.orphaned_metadata, result.images, result.image_bytes) == (2, 1, 1, 5)
