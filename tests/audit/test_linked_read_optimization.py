"""Regression and deterministic operation counts for the linked-work read path."""
from contextlib import contextmanager
from pathlib import Path

import pytest

from core import Game, Library
from controllers.metadata import MetadataControllerMixin
from database.work_repository import WorkDatabase

URL = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
STEAM = "https://store.steampowered.com/app/1091500/"

def legacy(db, game_id):
    link = db.get_link(game_id)
    return db.get_official_work(*link) if link else None

@pytest.fixture
def db(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([
        {"store":"dlsite","code":"RJ123456","title":"Example","page_url":URL},
        {"store":"steam","code":"1091500","title":"Steam example","page_url":STEAM},
    ])
    db.save_official_image_urls("dlsite", "RJ123456", {"hero":"https://img.dlsite.jp/cover.jpg"})
    return db

@pytest.mark.parametrize("link", [
    None, ("dlsite","RJ123456"), ("steam","1091500"),
    (" DLSITE "," rj123456 "), ("dlsite","RJ999999"),
    ("steam","999999"), ("unknown","RJ123456"),
])
def test_linked_read_matches_existing_contract(db, link):
    if link:
        with db.connect() as conn:
            conn.execute("INSERT INTO library_links(game_id,store,code) VALUES (?,?,?)", ("g",*link))
    assert db.get_linked_official_work("g") == legacy(db, "g")

def test_invalid_url_and_deleted_link_not_accepted(db):
    assert db.save_verified_game_link("g","dlsite","RJ123456")
    with db.connect() as conn:
        conn.execute("UPDATE works SET page_url=? WHERE store='dlsite'", ("https://fake.invalid/RJ123456",))
    assert db.get_linked_official_work("g") is None
    with db.connect() as conn:
        conn.execute("DELETE FROM library_links WHERE game_id='g'")
    assert db.get_linked_official_work("g") is None

def test_one_connection_and_one_select_per_normal_link(db, monkeypatch):
    assert db.save_verified_game_link("g","dlsite","RJ123456")
    original = db.connect
    connections, statements = [], []
    @contextmanager
    def counted():
        connections.append(1)
        with original() as conn:
            conn.set_trace_callback(lambda sql: statements.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
            yield conn
    monkeypatch.setattr(db,"connect",counted)
    expected = legacy(db,"g")
    old = len(connections),len(statements)
    connections.clear()
    statements.clear()
    assert db.get_linked_official_work("g") == expected
    new = len(connections),len(statements)
    assert old == (2,2)
    assert new == (1,1)
    print("LINKED_READ_CONNECTIONS",old[0],"->",new[0],"SELECTS",old[1],"->",new[1])

def test_controller_respects_manual_clear_and_current_db_values(db,tmp_path):
    library=Library(tmp_path/"data")
    game=Game("g","Example RJ123456",tmp_path)
    class Stub(MetadataControllerMixin):
        def current(self): return game
    stub=Stub()
    stub.library,stub.work_db=library,db
    assert stub.collected_game_record() is None
    assert db.save_verified_game_link("g","dlsite","RJ123456")
    record=stub.collected_game_record()
    assert record["code"]=="RJ123456"
    assert stub.has_official_image_candidates()
    with db.connect() as conn:
        conn.execute("UPDATE works SET images_json='[]' WHERE store='dlsite'")
    assert not stub.has_official_image_candidates()
    library.update_meta(game,product_code="")
    assert stub.collected_game_record() is None
    assert not stub.has_official_image_candidates()
