"""Batch official lookup: verified identity, bounded SQL, and DB-only worker."""
from contextlib import contextmanager
import pytest

from database.work_repository import WorkDatabase
from workers import title as titles

URL = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
STEAM = "https://store.steampowered.com/app/1091500/"

@pytest.fixture
def db(tmp_path):
    db=WorkDatabase(tmp_path/"data")
    db._upsert_verified([
        {"store":"dlsite","code":"RJ123456","title":"Japanese title","page_url":URL},
        {"store":"steam","code":"1091500","title":"Steam title","page_url":STEAM},
    ])
    with db.connect() as conn:
        conn.execute("UPDATE works SET titles_json=? WHERE store='dlsite'",
                     ('{"ja":"Japanese title","ko":"한국어 제목"}',))
        conn.execute("INSERT INTO works(store,code,title,page_url) VALUES(?,?,?,?)",
                     ("dlsite","RJ654321","Unverified","https://fake.invalid/RJ654321"))
        conn.executemany("INSERT INTO library_links(game_id,store,code) VALUES(?,?,?)",[
            ("a","dlsite","RJ123456"),("b","steam","1091500"),
            ("legacy"," DLSITE "," rj123456 "),("invalid","dlsite","RJ654321"),
            ("missing","dlsite","RJ999999"),("unknown","other","123456"),
        ])
    return db

def test_batch_matches_single_verified_lookup(db):
    ids=["a","b","legacy","invalid","missing","unknown","absent","a"]
    expected={g:r for g in ids if (r:=db.get_linked_official_work(g)) is not None}
    assert db.get_linked_official_works(ids)==expected
    keys=[(" DLSITE ","rj123456"),("steam","1091500"),("dlsite","RJ654321"),
          ("dlsite","RJ999999"),("other","123456"),("dlsite","RJ123456")]
    expected={(r["store"],r["code"]):r for store,code in keys
              if (r:=db.get_official_work(store,code)) is not None}
    assert db.get_official_works(keys)==expected
    assert db.get_linked_official_works([])=={}
    assert db.get_official_works([])=={}

def test_batch_link_connection_and_select_counts(db,monkeypatch):
    with db.connect() as conn:
        conn.executemany("INSERT INTO library_links(game_id,store,code) VALUES(?,?,?)",
                         [(f"g{i}","dlsite","RJ123456") for i in range(1000)])
    original=db.connect
    counts={"connections":0,"selects":0}
    def trace(sql):
        if sql.lstrip().upper().startswith(("SELECT","WITH")):
            counts["selects"]+=1
    @contextmanager
    def counted():
        counts["connections"]+=1
        with original() as conn:
            conn.set_trace_callback(trace)
            yield conn
    monkeypatch.setattr(db,"connect",counted)
    ids=[f"g{i}" for i in range(1000)]
    expected={}
    for game_id in ids:
        link=db.get_link(game_id)
        expected[game_id]=db.get_official_work(*link)
    assert counts=={"connections":2000,"selects":2000}
    counts.update(connections=0,selects=0)
    assert db.get_linked_official_works(ids)==expected
    assert counts=={"connections":1,"selects":3}
    print("BULK_LINK_PREFLIGHT_CONNECTIONS 2000 -> 1; SELECTS 2000 -> 3")
    counts.update(connections=0,selects=0)
    assert len(db.get_official_works([("dlsite","RJ123456")]*1000))==1
    assert counts=={"connections":1,"selects":1}
    print("DUPLICATE_WORK_KEYS 1000 -> 1")

def test_bulk_distinct_identity_chunks(db,monkeypatch):
    rows=[{"store":"steam","code":str(100000+i),"title":f"Game {i}",
           "page_url":f"https://store.steampowered.com/app/{100000+i}/"}
          for i in range(850)]
    db._upsert_verified(rows)
    keys=[("steam",r["code"]) for r in rows]
    actual=db.get_official_works(keys)
    assert len(actual)==850
    assert actual[keys[-1]]["title"]=="Game 849"

def test_worker_reuses_preview_snapshot_without_db_or_network(db,monkeypatch):
    from PySide6.QtWidgets import QApplication
    qt=QApplication.instance() or QApplication([])
    records=db.get_official_works([("dlsite","RJ123456"),("steam","1091500")])
    def forbidden(*args,**kwargs):
        raise AssertionError("Preview must not reopen DB or request network")
    monkeypatch.setattr(WorkDatabase,"__init__",forbidden)
    monkeypatch.setattr(titles,"lookup_localized_title",forbidden)
    worker=titles.BulkTitleWorker([
        ("a","Original A","RJ123456","dlsite"),
        ("b","Original B","1091500","steam"),
        ("c","Original C","RJ123456","dlsite"),
    ],"ko",db.path.parent/"localized_product_titles.json",db_only=True,verified_records=records)
    output=[];progress=[]
    worker.complete.connect(output.append)
    worker.progress.connect(lambda *args:progress.append(args))
    worker.run()
    assert [r["game_id"] for r in output[0]]==["a","b","c"]
    assert [r["title"] for r in output[0]]==["한국어 제목","Steam title","한국어 제목"]
    assert [r["language"] for r in output[0]]==["ko","en","ko"]
    assert len(progress)==3

def test_standalone_db_only_worker_batches_and_handles_missing(db,monkeypatch):
    from PySide6.QtWidgets import QApplication
    qt=QApplication.instance() or QApplication([])
    original=WorkDatabase.get_official_works
    calls=[]
    def counted(self,keys):
        keys=list(keys)
        calls.append(keys)
        return original(self,keys)
    monkeypatch.setattr(WorkDatabase,"get_official_works",counted)
    def forbidden(*args,**kwargs):
        raise AssertionError("DB-only worker must not request network")
    monkeypatch.setattr(titles,"lookup_localized_title",forbidden)
    worker=titles.BulkTitleWorker([
        ("a","A","RJ123456","dlsite"),("b","B","RJ999999","dlsite"),
        ("c","C","1091500","steam")],
        "ja",db.path.parent/"localized_product_titles.json",db_only=True)
    output=[]
    worker.complete.connect(output.append)
    worker.run()
    assert len(calls)==1 and len(calls[0])==3
    assert output[0][0]["title"]=="Japanese title"
    assert "error" in output[0][1]
    assert output[0][2]["language"]=="en"

def test_snapshot_reflects_changes_on_next_lookup(db):
    assert db.get_linked_official_works(["a"])["a"]["title"]=="Japanese title"
    with db.connect() as conn:
        conn.execute("UPDATE works SET title='New title' WHERE store='dlsite' AND code='RJ123456'")
    assert db.get_linked_official_works(["a"])["a"]["title"]=="New title"
    with db.connect() as conn:
        conn.execute("DELETE FROM library_links WHERE game_id='a'")
    assert db.get_linked_official_works(["a"])=={}
