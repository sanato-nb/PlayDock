"""AI import is data-only, requires exact local target, and verifies before persistence."""
import json
import pytest
from core import Game, Library
from database.work_repository import WorkDatabase
from services.identity_import_service import prepare_identity_import, collect_import_batch
from services.catalog_collection_service import CatalogCollector, game_catalog_entries, partition_catalog_entries
from integrations.official_lookup.code_only import Work, Result, codes_in, steam_ids_in

DL="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
ST="https://store.steampowered.com/app/1091500/"

@pytest.fixture
def fixture(tmp_path):
    lib=Library(tmp_path/"data")
    db=WorkDatabase(lib.store)
    archive=tmp_path/"Sample [v1].zip";archive.write_bytes(b"untouched")
    game=Game("sample",archive.stem,tmp_path,archive=archive)
    lib.update_meta(game,title="manual display",launch_args="--test")
    return lib,db,game

def row(game,**kwargs):
    return {"original_filename":game.archive.name,"store":"dlsite","product_code":"RJ123456",
            "status":"confirmed","official_title":"Example","official_url":DL,**kwargs}

def payload(*rows):
    return json.dumps({"format":"PlayDock_Identity_Import","version":1,"games":rows})

def fake_factory(calls,works=True):
    def build(db):
        def checker(item,*,cache):
            calls.append(item.label)
            ids=codes_in(item.label)
            store,code=("dlsite",ids[0]) if ids else ("steam",steam_ids_in(item.label)[0])
            if not works:
                return Result(item.label,item.origin,"excluded")
            return Result(item.label,item.origin,"confirmed",
                (Work(code,"Official", "game",DL if store=="dlsite" else ST,"verified",store),),
                selected_store=store)
        return CatalogCollector(db,checker=checker,dlsite_detail=lambda code:{},steam_art=lambda code:{})
    return build

@pytest.mark.parametrize("store,code,url",[("dlsite","RJ123456",DL),("steam","1091500",ST)])
def test_import_and_recollect_preserves_original(fixture,store,code,url):
    lib,db,g=fixture
    before=lib.meta(g)
    proposals,rejected=prepare_identity_import(payload(row(g,store=store,product_code=code,official_url=url)),lib,[g],db)
    assert len(proposals)==1 and not rejected
    assert lib.meta(g)==before and db.get_link(g.id) is None
    calls=[]
    events=collect_import_batch(proposals,lib,db.path,collector_factory=fake_factory(calls))
    assert events[0].connected and db.get_link(g.id)==(store,code)
    assert db.get_linked_official_work(g.id)["title"]=="Official"
    meta=lib.meta(g)
    assert meta["product_code"]==code and meta["product_store"]==store
    assert meta["title"]==before["title"] and meta["launch_args"]==before["launch_args"]
    assert g.archive.read_bytes()==b"untouched" and len(calls)==1
    eligible,missing=partition_catalog_entries(game_catalog_entries(lib,[g]))
    assert len(eligible)==1 and not missing
    assert db.get_link(g.id)==(store,code)
    assert not prepare_identity_import(payload(row(g)),lib,[g],db)[0]

@pytest.mark.parametrize("change",[
    {"status":"needs_review"},{"status":"unconfirmed"},{"original_filename":"Other.zip"},
    {"original_filename":"../Sample [v1].zip"},{"store":"unknown"},
    {"product_code":"RJ000"},{"official_url":"https://evil.example/RJ123456.html"},
    {"official_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ1234567.html"},
    {"official_title":None}])
def test_rejects_invalid_and_uncertain(fixture,change):
    lib,db,g=fixture
    p,r=prepare_identity_import(payload(row(g,**change)),lib,[g],db)
    assert not p and r and db.get_link(g.id) is None and "product_code" not in lib.meta(g)

def test_duplicate_and_manual_clear(fixture):
    lib,db,g=fixture
    assert not prepare_identity_import(payload(row(g),row(g)),lib,[g],db)[0]
    lib.update_meta(g,product_code="")
    assert not prepare_identity_import(payload(row(g)),lib,[g],db)[0]

def test_failed_lookup_does_not_store(fixture):
    lib,db,g=fixture
    p,_=prepare_identity_import(payload(row(g)),lib,[g],db)
    result=collect_import_batch(p,lib,db.path,collector_factory=fake_factory([],False))
    assert result[0].outcome=="excluded" and not result[0].connected
    assert "product_code" not in lib.meta(g) and db.get_link(g.id) is None

def test_changed_meta_after_preview_is_protected(fixture):
    lib,db,g=fixture
    p,_=prepare_identity_import(payload(row(g)),lib,[g],db)
    lib.update_meta(g,product_code="RJ654321")
    calls=[]
    assert not collect_import_batch(p,lib,db.path,collector_factory=fake_factory(calls))[0].connected
    assert calls==[] and lib.meta(g)["product_code"]=="RJ654321"

def test_rejects_invalid_json_and_duplicate_keys(fixture):
    lib,db,g=fixture
    for text in ("not json",'{"format":"PlayDock_Identity_Import","version":1,"version":1,"games":[]}'):
        with pytest.raises(ValueError):
            prepare_identity_import(text,lib,[g],db)

def test_dialog_import_only_after_completion(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ui.dialogs.catalog_collection import CatalogCollectionDialog
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    d=CatalogCollectionDialog(0,excluded_no_code=("Sample.zip",),prompt_text="prompt")
    assert not d.import_button.isEnabled()
    d.on_complete([],False)
    assert d.import_button.isEnabled()
    hits=[];d.importRequested.connect(lambda:hits.append(True))
    d.import_button.click()
    assert hits==[True]
    d.close()
