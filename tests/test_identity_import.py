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
    {"status":"needs_review"},{"status":"needs_review","reason":"candidate","product_code":None},
    {"status":"unconfirmed"},{"original_filename":"Other.zip"},
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


def test_import_rechecks_even_if_work_exists(fixture):
    lib,db,g=fixture
    db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Cached",
                         "page_url":DL}])
    p,_=prepare_identity_import(payload(row(g)),lib,[g],db)
    calls=[]
    events=collect_import_batch(p,lib,db.path,collector_factory=fake_factory(calls,False))
    assert len(calls)==1 and not events[0].connected
    assert db.get_link(g.id) is None and "product_code" not in lib.meta(g)


def test_optional_reason_field_remains_compatible(fixture):
    lib, db, game = fixture
    suggestions, rejected = prepare_identity_import(
        payload(row(game, reason="Official title and ID confirmed")), lib, [game], db)
    assert len(suggestions) == 1 and not rejected
    assert "product_code" not in lib.meta(game)


def test_review_candidate_requires_final_approval(fixture):
    from services.identity_import_service import approve_verified_import
    lib,db,g=fixture
    p,r=prepare_identity_import(payload(row(g,status="needs_review",reason="Official URL indexed; page blocked")),lib,[g],db)
    assert len(p)==1 and not r and p[0].reason
    events=collect_import_batch(p,lib,db.path,collector_factory=fake_factory([]),verify_only=True)
    assert events[0].outcome=="fetched" and not events[0].connected
    assert "product_code" not in lib.meta(g) and db.get_link(g.id) is None
    assert approve_verified_import([],events,lib,db)==[]
    result=approve_verified_import(p,events,lib,db)
    assert result[0].connected and lib.meta(g)["product_code"]=="RJ123456"
    assert g.archive.read_bytes()==b"untouched"


def test_review_reason_and_checkbox_selection(fixture,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ui.dialogs.identity_import import IdentityImportPreviewDialog
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    lib,db,g=fixture
    p,r=prepare_identity_import(payload(row(g,status="unconfirmed",reason="No official match")),lib,[g],db)
    assert not p and "No official match" in r[0]
    p,r=prepare_identity_import(payload(row(g,status="needs_review",reason="candidate")),lib,[g],db)
    d=IdentityImportPreviewDialog(p,r)
    try:
        assert not d.selected_proposals() and not d.confirm.isEnabled()
        d.select_all(True)
        assert d.selected_proposals()==p and d.confirm.isEnabled()
        d.select_all(False)
        assert not d.selected_proposals()
    finally:
        d.close()


@pytest.mark.parametrize("approve",[False,True])
def test_controller_final_approval_and_remaining_count(fixture,monkeypatch,approve):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QWidget,QDialog
    import controllers.catalog_collection as module
    from ui.dialogs.catalog_collection import CatalogCollectionDialog
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    lib,db,g=fixture
    proposals,_=prepare_identity_import(payload(row(g,status="needs_review",reason="candidate")),lib,[g],db)
    events=collect_import_batch(proposals,lib,db.path,collector_factory=fake_factory([]),verify_only=True)
    class Preview:
        def __init__(self,items,rejected,parent,*,official_titles):
            assert db.get_link(g.id) is None
            assert official_titles[g.id]=="Official"
            self.items=items
        def exec(self):
            return QDialog.DialogCode.Accepted if approve else QDialog.DialogCode.Rejected
        def selected_proposals(self):
            return self.items
    monkeypatch.setattr(module,"IdentityImportPreviewDialog",Preview)
    class Host(QWidget,module.CatalogCollectionControllerMixin):
        def reload(self,**kwargs):
            pass
    host=Host()
    host.games=[g];host.library=lib;host.work_db=db;host.selected_id=g.id
    dialog=CatalogCollectionDialog(1,host)
    dialog.import_mode=True
    host.catalog_dialog=dialog
    host.catalog_worker=SimpleNamespace(import_library=lib,import_events=events,
        import_interrupted=False,import_error="",entries=proposals,deleteLater=lambda:None)
    try:
        host.catalog_collection_finished()
        assert (db.get_link(g.id) is not None)==approve
        assert len(dialog.no_code)==(0 if approve else 1)
        assert dialog.import_button.isEnabled()==(not approve)
        assert "남은 품번 없는 게임" in dialog.summary.text()
    finally:
        dialog.close()
        host.close()


def test_compact_preview_keeps_complete_evidence_and_selection(fixture,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ui.dialogs.identity_import import IdentityImportPreviewDialog, CandidateCheckDelegate
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    lib,db,g=fixture
    reason="Detailed evidence "*40
    p,_=prepare_identity_import(payload(row(g,status="needs_review",reason=reason)),lib,[g],db)
    d=IdentityImportPreviewDialog(p,["Other.zip — lookup failed"],official_titles={g.id:"Official"})
    try:
        assert d.table.columnCount()==4 and d.table.rowHeight(0)==44
        assert isinstance(d.table.itemDelegateForColumn(0),CandidateCheckDelegate)
        assert p[0].reason in d.evidence.toPlainText()
        assert "Official" in d.evidence.toPlainText()
        assert "Other.zip" in d.excluded_details.toPlainText()
        d.select_all(True)
        assert d.selection_count.text()=="선택 1개"
        assert d.selected_proposals()==p
    finally:
        d.close()


def test_final_preview_receives_failed_lookup(fixture,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QWidget,QDialog
    import controllers.catalog_collection as module
    from ui.dialogs.catalog_collection import CatalogCollectionDialog
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    lib,db,g=fixture
    p,_=prepare_identity_import(payload(row(g,status="needs_review",reason="candidate")),lib,[g],db)
    events=collect_import_batch(p,lib,db.path,collector_factory=fake_factory([],False),verify_only=True)
    seen=[]
    class Preview:
        def __init__(self,items,rejected,parent,*,official_titles):
            assert not items and not official_titles
            seen.extend(rejected)
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr(module,"IdentityImportPreviewDialog",Preview)
    class Host(QWidget,module.CatalogCollectionControllerMixin):
        def reload(self,**kwargs): pass
    host=Host()
    host.games=[g];host.library=lib;host.work_db=db;host.selected_id=g.id
    dialog=CatalogCollectionDialog(1,host)
    dialog.import_mode=True
    host.catalog_dialog=dialog
    host.catalog_worker=SimpleNamespace(import_library=lib,import_events=events,
        import_interrupted=False,import_error="",entries=p,deleteLater=lambda:None)
    try:
        host.catalog_collection_finished()
        assert len(seen)==1 and g.archive.name in seen[0]
        assert "재확인 실패" in seen[0]
        assert db.get_link(g.id) is None and len(dialog.no_code)==1
    finally:
        dialog.close()
        host.close()
