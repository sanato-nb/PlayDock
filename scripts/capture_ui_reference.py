"""Capture synthetic, offline PlayDock UI evidence in a fixed Qt environment."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    source=args.source.resolve()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(source/"src/playdock"),str(source)]
    from PySide6.QtCore import Qt, QTranslator, QLibraryInfo
    from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QPushButton
    from PIL import Image
    import app as launcher
    from core import Library
    from ui.dialogs.file_dialog import PlayDockFileDialog
    from ui.dialogs.title import BulkTitleSettingsDialog
    from ui.dialogs.folder_settings import FirstRunDialog
    from ui.dialogs.catalog_collection import CatalogCollectionDialog
    from ui.dialogs.database_status import DatabaseStatusDialog

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs,True)
    qt=QApplication([])
    translator=QTranslator(qt)
    if translator.load("qtbase_ko",QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        qt.installTranslator(translator)
    qt.setStyle("Fusion")
    qt.setStyleSheet(launcher.STYLESHEET)
    contract={"style_sha256":hashlib.sha256(qt.styleSheet().encode()).hexdigest(),"screens":{},"menus":{}}
    def capture(name,widget):
        widget.show()
        qt.processEvents()
        image=widget.grab()
        assert not image.isNull() and image.save(str(out/(name+".png")))
        contract["screens"][name]={"title":widget.windowTitle(),
            "minimum":[widget.minimumWidth(),widget.minimumHeight()],
            "size":[widget.width(),widget.height()],
            "buttons":[{"text":b.text(),"object":b.objectName(),"enabled":b.isEnabled(),
                        "visible":b.isVisible()} for b in widget.findChildren(QPushButton)]}
    def menu_rows(menu):
        return [{"text":a.text(),"enabled":a.isEnabled(),"separator":a.isSeparator(),
                 "checked":a.isChecked(),"children":menu_rows(a.menu()) if a.menu() else []}
                for a in menu.actions()]
    def menu(name,button,open_menu):
        captured=[]
        original=button.present_popup
        button.present_popup=lambda m,**kw:captured.append(m)
        try:
            open_menu()
            assert len(captured)==1
            m=captured[0]
            contract["menus"][name]=menu_rows(m)
            m.ensurePolished()
            m.adjustSize()
            assert m.grab().save(str(out/(name+".png")))
        finally:
            button.present_popup=original
    with tempfile.TemporaryDirectory(prefix="playdock-ui-reference-") as tmp:
        root=Path(tmp)
        archives=root/"archives";archives.mkdir()
        installed=root/"installed";installed.mkdir()
        (archives/"Example Game [RJ123456].zip").write_bytes(b"fixture")
        (archives/"Second Game.7z").write_bytes(b"fixture")
        library=Library(root/"data")
        library.change_root(installed);library.change_archive_root(archives)
        launcher.Library=lambda:library
        window=launcher.MainWindow()
        window.resize(1380,840)
        game=next(g for g in window.games if "RJ123456" in g.name)
        window.populate_games(game.id)
        contract["layout"]={"main_minimum":[window.minimumWidth(),window.minimumHeight()],
            "sidebar_minimum":window.findChild(QFrame,"Sidebar").minimumWidth(),
            "footer_height":window.findChild(QFrame,"FooterBar").height(),
            "tree_icon":[window.tree.iconSize().width(),window.tree.iconSize().height()],
            "search_placeholder":window.search.placeholderText(),
            "function_initial_enabled":window.function_menu_btn.isEnabled()}
        capture("01_library_no_official_data",window)
        menu("02_settings_menu",window.settings_menu_btn,window.show_settings_menu)
        menu("03_game_management_before_collection",window.extra_menu_btn,window.show_extra_menu)
        menu("04_sort_menu",window.sort_button,window.open_sort_menu)
        menu("05_function_disabled",window.function_menu_btn,window.show_function_menu)
        page="https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
        window.work_db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Example Game","page_url":page}])
        assert window.work_db.save_verified_game_link(game.id,"dlsite","RJ123456")
        window.work_db.save_official_image_urls("dlsite","RJ123456",{"hero":"https://img.dlsite.jp/cover.jpg"})
        art=library.art_dir(game)
        Image.new("RGB",(1600,520),"#456c88").save(art/"hero.png")
        Image.new("RGB",(256,256),"#6984a2").save(art/"icon.png")
        window.populate_games(game.id)
        capture("06_library_with_official_data",window)
        menu("07_function_enabled",window.function_menu_btn,window.show_function_menu)
        menu("08_game_management_after_collection",window.extra_menu_btn,window.show_extra_menu)
        cid=window.collections.create("Example Collection")
        window.collections.set_game_memberships(game.id,{cid})
        window.reload(prefer_id=game.id)
        window.show_collections_overview()
        capture("09_collections",window)
        window.show_all_games()
        for name,dialog in [
            ("10_official_name_dialog",BulkTitleSettingsDialog(library,window.games,None,window)),
            ("11_folder_settings",FirstRunDialog(library,window)),
            ("12_collection_progress",CatalogCollectionDialog(1,window,excluded_no_code=["Second Game.7z"],prompt_text="Synthetic prompt")),
            ("13_database_status",DatabaseStatusDialog(library.store,len(window.games),parent=window)),
            ("14_file_picker",PlayDockFileDialog(window,"이미지 선택",str(art),"이미지 (*.png)")),
        ]:
            capture(name,dialog)
            dialog.hide()
        window.close()
        qt.processEvents()
    (out/"ui_contract.json").write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding="utf-8")
    print("UI_REFERENCE_CAPTURED",len(contract["screens"]),len(contract["menus"]))

if __name__=="__main__":
    main()
