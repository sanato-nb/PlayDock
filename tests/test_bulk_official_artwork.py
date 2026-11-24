"""Bulk scope, explicit choices, overwrite safety and partial failure."""
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from core import Library, Game
from database.work_repository import WorkDatabase
from services.bulk_official_artwork import apply_bulk_artwork
from ui.dialogs.bulk_official_artwork import BulkOfficialArtworkDialog

URL="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
ART="https://img.dlsite.jp/cover.jpg"


def setup(tmp_path):
    lib=Library(tmp_path/"data")
    db=WorkDatabase(lib.store)
    db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Example","page_url":URL}])
    db.save_official_image_urls("dlsite","RJ123456",{"hero":ART,"icon":ART})
    games=[Game("g1","One",tmp_path),Game("g2","Two",tmp_path)]
    for g in games:
        assert db.save_verified_game_link(g.id,"dlsite","RJ123456")
    return lib,db,games


def test_dialog_defaults_unchecked_and_selects_only_missing(tmp_path,monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    lib,db,games=setup(tmp_path)
    rec=db.get_linked_official_work(games[0].id)
    d=BulkOfficialArtworkDialog([(games[0],rec,{"hero","icon"},{"hero"}),
                                 (games[1],rec,{"hero"},set())])
    try:
        assert not d.selected_jobs() and not d.apply_button.isEnabled()
        d.select_missing()
        assert [j[2] for j in d.selected_jobs()]==[{"icon"},{"hero"}]
        assert all(not j[3] for j in d.selected_jobs())
        d.table.item(0,2).setCheckState(Qt.CheckState.Checked)
        assert d.selected_jobs()[0][3]=={"hero"}
        d.clear_selection()
        assert not d.selected_jobs()
    finally:
        d.close()


def test_bulk_does_not_touch_existing_unapproved_or_unselected(tmp_path):
    lib,db,games=setup(tmp_path)
    g=games[0]
    folder=lib.art_dir(g)
    (folder/"hero.png").write_bytes(b"original")
    calls=[]
    def prepare(work,*,candidates):
        assert candidates=={"icon":ART}
        return {"icon":object()}
    def apply(library,game,work,offers,selected):
        calls.append((game.id,selected))
        assert selected=={"icon"}
        return ["icon"]
    result=apply_bulk_artwork(lib,db.path,[(g,("dlsite","RJ123456"),{"hero","icon"},set())],
                             prepare=prepare,apply=apply)
    assert calls==[(g.id,{"icon"})]
    assert result[0]["applied"]==["icon"] and len(result[0]["skipped"])==1
    assert (folder/"hero.png").read_bytes()==b"original"


def test_bulk_rechecks_links_and_continues_after_download_failure(tmp_path):
    lib,db,games=setup(tmp_path)
    lib.update_meta(games[0],product_code="")
    seen=[]
    def prepare(work,*,candidates):
        seen.append(candidates)
        return {}
    result=apply_bulk_artwork(lib,db.path,[(g,("dlsite","RJ123456"),{"hero"},set()) for g in games],
                             prepare=prepare)
    assert seen==[{"hero":ART}]
    assert len(result)==2 and all(not r["applied"] and r["skipped"] for r in result)
