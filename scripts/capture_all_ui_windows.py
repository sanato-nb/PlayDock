"""Native Windows UI screenshot inventory. Only disposable synthetic data."""
from pathlib import Path
from types import SimpleNamespace as NS
from io import BytesIO
import argparse
import html
import json
import os
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src/playdock"), str(ROOT)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    def record(name, label, kind, action):
        try:
            file = out / (name + ".png")
            size = action(file)
            rows.append(dict(file=file.name, label=label, kind=kind, size=list(size)))
            print("CAPTURED", name, size, flush=True)
        except Exception:
            failures.append(dict(name=name, label=label, error=traceback.format_exc()))
            print("CAPTURE_FAILED", name, failures[-1]["error"], flush=True)

    def publish():
        (out / "manifest.json").write_text(json.dumps({
            "source": os.environ.get("GITHUB_SHA", ""),
            "data": "synthetic local fixtures; no real game or network operations",
            "screens": rows, "failures": failures
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        cards = "".join(f'<section><h2>{html.escape(r["label"])}</h2><p>{html.escape(r["kind"])} · {r["size"]}</p><a href="{r["file"]}"><img src="{r["file"]}" loading="lazy"></a></section>' for r in rows)
        errors = "".join(f'<li>{html.escape(r["name"])}: {html.escape(r["error"])}</li>' for r in failures)
        (out / "index.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>PlayDock UI 검수</title><style>body{font:16px system-ui;margin:24px;background:#151d25;color:#e8eef5}section{margin:24px 0}img{max-width:100%;height:auto}h2{font-size:18px}p{color:#b3c5d5}</style><h1>PlayDock Windows UI 검수</h1><p>실제 UI 클래스 / 합성 데이터 / 설치·삭제 미실행</p><p>성공 '+str(len(rows))+' / 실패 '+str(len(failures))+'</p>'+cards+'<h2>실패 내역</h2><ul>'+errors+'</ul></html>', encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="playdock-ui-review-") as tmp:
        root = Path(tmp)
        try:
            qt_capture(root, record)
        except Exception:
            failures.append(dict(name="qt-session", label="Qt 실행", error=traceback.format_exc()))
        publish()
        try:
            tk_capture(root, record)
        except Exception:
            failures.append(dict(name="tk-session", label="설치기·제거기 실행", error=traceback.format_exc()))
        publish()
    print("SCREENSHOT_SUMMARY", len(rows), len(failures), flush=True)
    if failures:
        raise SystemExit(1)


def qt_capture(root, record):
    from PySide6.QtCore import Qt, QTranslator, QLibraryInfo, QCoreApplication, QEvent
    from PySide6.QtGui import QFontDatabase, QRawFont, QFont, QPixmapCache
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from PIL import Image
    import app as launcher
    from core import Library
    from ui.dialogs.common import TextEntryDialog, ChoiceDialog, MessageDialog
    from ui.dialogs.file_dialog import PlayDockFileDialog
    from ui.dialogs.title import BulkTitleSettingsDialog
    from ui.dialogs.title_preview import BulkPreviewDialog, KoreanWebCandidatesDialog
    from ui.dialogs.folder_settings import FirstRunDialog
    from ui.dialogs.catalog_collection import CatalogCollectionDialog
    from ui.dialogs.database_status import DatabaseStatusDialog
    from ui.dialogs.data_manager import DataManagerDialog
    from ui.dialogs.cache_manager import CacheManagerDialog
    from ui.dialogs.collection_settings import GameCollectionsDialog
    from ui.dialogs.library import LibraryInfoDialog
    from ui.dialogs.identity_import import IdentityImportDialog, IdentityImportPreviewDialog
    from ui.dialogs.identity_artwork import IdentityArtworkDialog
    from ui.dialogs.bulk_official_artwork import BulkOfficialArtworkDialog, BulkArtworkProgressDialog
    from ui.work_info_dialog import WorkPreviewDialog
    from services.identity_import_service import IdentitySuggestion
    from title_editor import TitleEditor
    from ui.widgets.launcher import collection_chevron

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    qt.setStyle("Fusion")
    qt.setStyleSheet(launcher.STYLESHEET)
    translator = QTranslator(qt)
    if translator.load("qtbase_ko", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        qt.installTranslator(translator)
    assert qt.platformName() == "windows", qt.platformName()
    print("NATIVE_FONT", QRawFont.fromFont(QFont("Malgun Gothic", 10)).familyName(),
          "Malgun Gothic" in QFontDatabase.families(), flush=True)
    archives = root / "archives"; archives.mkdir()
    installed = root / "installed"; installed.mkdir()
    lib = Library(root / "data")
    lib.change_root(installed); lib.change_archive_root(archives)
    lib.settings["first_run_complete"] = True; lib.save_settings()
    launcher.Library = lambda: lib
    window = launcher.MainWindow()
    window.resize(1380, 840)
    def grab(widget, file):
        widget.show()
        qt.processEvents()
        time.sleep(.10)
        qt.processEvents()
        pic = widget.grab()
        assert not pic.isNull() and pic.save(str(file))
        return pic.width(), pic.height()
    def shot(name, label, widget):
        record(name, label, "Qt Windows", lambda f: grab(widget, f))
    def dialog(name, label, factory, update=None):
        def capture(file):
            widget = factory()
            try:
                if update: update(widget)
                return grab(widget, file)
            finally:
                widget.hide()
                widget.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                qt.processEvents()
        record(name, label, "Qt Windows", capture)
    def menu(name, label, button, opener):
        def capture(file):
            opener()
            qt.processEvents()
            m = button._popup_menu
            assert m is not None
            try:
                return grab(m, file)
            finally:
                m.close(); qt.processEvents()
        record(name, label, "Qt Windows 메뉴", capture)

    shot("01_empty_library", "빈 라이브러리", window)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("README.txt", "Synthetic data only")
    for name in ["예시 게임 [RJ123456].zip", "품번 없는 예시 게임.zip", "또 다른 예시 게임.zip"]:
        (archives / name).write_bytes(buffer.getvalue())
    window.reload()
    game = next(g for g in window.games if "RJ123456" in g.name)
    other = next(g for g in window.games if "품번 없는" in g.name)
    window.populate_games(game.id)
    shot("02_library_no_official", "라이브러리 · 공식 정보 없음", window)
    menu("03_settings_menu", "설정 메뉴", window.settings_menu_btn, window.show_settings_menu)
    menu("04_game_menu_before", "게임 관리 · 수집 전", window.extra_menu_btn, window.show_extra_menu)
    menu("05_sort_menu", "정렬 메뉴", window.sort_button, window.open_sort_menu)
    menu("06_function_disabled", "전체 기능 · 비활성 상태", window.function_menu_btn, window.show_function_menu)
    page = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
    rec = {"store":"dlsite","code":"RJ123456","title":"공식 예시 게임","page_url":page}
    window.work_db._upsert_verified([rec])
    assert window.work_db.save_verified_game_link(game.id,"dlsite","RJ123456")
    window.work_db.save_official_image_urls("dlsite","RJ123456",{"hero":"https://img.dlsite.jp/cover.jpg"})
    art = lib.art_dir(game)
    Image.new("RGB",(1600,520),"#456c88").save(art/"hero.png")
    Image.new("RGB",(256,256),"#6984a2").save(art/"icon.png")
    window.populate_games(game.id)
    shot("07_library_official", "라이브러리 · 공식 정보 및 이미지", window)
    menu("08_function_enabled", "전체 기능 · 활성 상태", window.function_menu_btn, window.show_function_menu)
    menu("09_game_menu_after", "게임 관리 · 수집 후", window.extra_menu_btn, window.show_extra_menu)
    cid = window.collections.create("예시 모음집")
    window.collections.set_game_memberships(game.id, {cid})
    window.reload(prefer_id=game.id)
    window.show_collections_overview()
    shot("10_collections", "내 모음집", window)
    window.show_all_games()
    dialog("11_official_names","공식 게임명 일괄 설정",lambda: BulkTitleSettingsDialog(lib,window.games,None,window))
    dialog("12_folders","폴더 설정 마법사",lambda: FirstRunDialog(lib,window))
    def collection(): return CatalogCollectionDialog(3,window,excluded_no_code=["품번 없는 예시 게임.zip"],prompt_text="예시 AI 조사 프롬프트")
    dialog("13_collection_progress","게임 정보 수집 · 진행 중",collection,
           lambda w: w.on_progress(1,3,NS(outcome="cached",label=game.name,message="DB 재사용")))
    events=[NS(outcome="cached",connected=True,saved=0,enriched=0,label=game.name,message="DB 재사용"),
            NS(outcome="fetched",connected=True,saved=1,enriched=0,label=other.name,message="예시 확인"),
            NS(outcome="excluded",connected=False,saved=0,enriched=0,label="예시 실패",message="조회 실패 예시")]
    dialog("14_collection_done","게임 정보 수집 · 완료 및 AI 연동",collection,lambda w: (w.on_progress(3,3,events[2]),w.on_complete(events)))
    dialog("15_db_status","DB 상태 확인",lambda: DatabaseStatusDialog(lib.store,len(window.games),parent=window))
    dialog("16_file_picker","파일 선택",lambda: PlayDockFileDialog(window,"이미지 선택",str(art),"이미지 (*.png)"))
    dialog("17_folder_picker","폴더 선택",lambda: PlayDockFileDialog(window,"폴더 선택",str(root)),lambda w: w.setFileMode(QFileDialog.FileMode.Directory))
    dialog("18_library_info","라이브러리 속성",lambda: LibraryInfoDialog(lib,window.games,window))
    for i, label in enumerate(["게임 목록","모음집","캐시","백업"]):
        dialog(f"19_data_tab_{i+1}",f"데이터 관리 · {label}",lambda: DataManagerDialog(window),lambda w,i=i: w.tabs.setCurrentIndex(i))
    dialog("20_cache","이미지 캐시 관리",lambda: CacheManagerDialog(lib,window.games,window))
    dialog("21_memberships","게임 모음집 추가 / 제거",lambda: GameCollectionsDialog(window.collections,game,game.name,window))
    dialog("22_bulk_artwork","공식 이미지 일괄 적용",lambda: BulkOfficialArtworkDialog([(game,rec,{"hero","icon"},{"hero"}),(other,{"store":"steam","code":"620"},{"icon"},set())],window),lambda w:w.select_missing())
    dialog("23_bulk_artwork_progress","공식 이미지 일괄 적용 · 진행",lambda: BulkArtworkProgressDialog(NS(requestInterruption=lambda: None),3,window),lambda w:w.update_progress(1,3,game.name))
    work=NS(store="dlsite",title=rec["title"],code=rec["code"],category="게임",url=page)
    offers={k:NS(preview=(art/("hero.png" if k=="hero" else "icon.png")).read_bytes()) for k in ("hero","icon")}
    dialog("24_identity_artwork","개별 공식 배너·아이콘",lambda: IdentityArtworkDialog(work,offers,existing_kinds={"hero"},parent=window))
    dialog("25_identity_import","AI 조사 결과 가져오기",lambda: IdentityImportDialog(window),lambda w:w.edit.setPlainText(json.dumps({"format":"PlayDock_Identity_Import","version":1,"note":"합성 예시"},ensure_ascii=False,indent=2)))
    p=IdentitySuggestion(other,other.archive.name,"steam","620","예시 후보","https://store.steampowered.com/app/620/","needs_review","합성 검수용 조사 근거")
    dialog("26_identity_candidates","품번 등록 후보 확인",lambda: IdentityImportPreviewDialog([p],["예시 미확인 게임"],window),lambda w:w.select_all(True))
    dialog("27_identity_verified","공식 조회 결과 확인",lambda: IdentityImportPreviewDialog([p],[],window,official_titles={other.id:"공식 예시 작품"}),lambda w:w.select_all(True))
    dialog("28_work_preview","작품 정보 확인",lambda: WorkPreviewDialog({**rec,"maker":"예시 제작사","tags":["게임"],"titles":{"ko":"예시 작품"}},parent=window))
    dialog("29_title_lookup","기존 이름 조회 결과 (호환)",lambda: BulkPreviewDialog([{"original":"예시 원본","title":"예시 작품","language":"ko","source":"합성"}],"ko",window))
    dialog("30_korean_candidates","기존 한국어 검색 후보 (호환)",lambda: KoreanWebCandidatesDialog([NS(title="예시 한국어 제목",url="https://example.com",page_title="예시",excerpt="합성 데이터")],window))
    dialog("31_title_editor","기존 상세 이름 편집기",lambda: TitleEditor(game.id,library=lib))
    dialog("32_single_title","개별 게임 이름 설정",lambda: TitleEditor(game.id,library=lib,single_game_only=True))
    dialog("33_manual_title","수동 이름 변경 입력",lambda: TextEntryDialog("게임 이름 변경","표시할 게임 이름을 입력하세요.",window,game.name))
    dialog("34_launch_options","실행 옵션 입력",lambda: TextEntryDialog("게임 실행 옵션","EXE에 전달할 인수 (명령어가 아닌 인수만)",window,""))
    dialog("35_executable_choice","실행 파일 선택",lambda: ChoiceDialog("실행파일 선택","게임 실행 파일을 선택하세요:",["Game.exe","Launcher.exe"],0,window))
    dialog("36_install_confirm","게임 설치 확인",lambda: MessageDialog("게임 설치","예시 압축파일을 해제합니다. 원본은 삭제하지 않습니다.",window,yes_no=True,yes_label="Yes",no_label="No"))
    dialog("37_remove_confirm","게임 설치 제거 확인",lambda: MessageDialog("게임 설치 제거","예시 설치 폴더를 휴지통으로 이동합니다.",window,yes_no=True,yes_label="휴지통으로 이동",no_label="취소"))
    dialog("38_archive_password","암호화 압축 비밀번호 입력 (공통 입력창)",lambda: TextEntryDialog("압축파일 비밀번호","예시 압축파일의 비밀번호를 입력하세요.",window),lambda w:w.edit.setEchoMode(w.edit.EchoMode.Password))
    dialog("39_first_launch","첫 실행 확인",lambda: MessageDialog("첫 실행 확인","예시 실행 파일을 실행할까요?",window,yes_no=True))
    dialog("40_notice","안내 메시지",lambda: MessageDialog("설치 완료","예시 작업이 완료되었습니다.",window))
    dialog("41_error","오류 메시지 (Qt 기본)",lambda: QMessageBox(QMessageBox.Icon.Warning,"오류","예시 오류 메시지",QMessageBox.StandardButton.Ok,window))
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    if hasattr(collection_chevron,"cache_clear"): collection_chevron.cache_clear()
    QPixmapCache.clear()


def tk_capture(root, record):
    import ctypes
    from PIL import ImageGrab
    import setup_wizard as setup
    import uninstall_wizard as uninstall
    setup.existing_or_default = lambda: (str(root / "archives"),str(root / "installed"))
    setup.app_install_directory = lambda: root / "program"
    uninstall.app_install_directory = lambda: root / "program"
    def grab(window, file):
        window.update_idletasks(); window.update()
        window.lift()
        time.sleep(.2)
        window.update()
        hwnd = window.winfo_id()
        api = ctypes.windll.user32.GetAncestor
        api.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        api.restype = ctypes.c_void_p
        hwnd = api(hwnd, 2) or hwnd
        try:
            image = ImageGrab.grab(window=hwnd)
        except (TypeError,OSError):
            x,y=window.winfo_rootx(),window.winfo_rooty()
            image=ImageGrab.grab(bbox=(x,y,x+window.winfo_width(),y+window.winfo_height()))
        assert image.width>100 and image.height>100
        assert len(set(image.resize((30,30)).getdata()))>10, "Blank Tk capture"
        image.save(file)
        return image.size
    wizard = setup.SetupWizard()
    try:
        for page,label in enumerate(["설치 시작","설치 위치","설치 중 (상태 미리보기)","설치 완료 (상태 미리보기)"]):
            def capture(file,page=page):
                wizard.page=page
                wizard.render()
                return grab(wizard,file)
            record(f"42_setup_{page}",label,"Tk Windows · 설치 미실행",capture)
    finally:
        wizard.destroy()
    wizard = uninstall.UninstallWizard()
    try:
        record("43_uninstaller","제거 프로그램","Tk Windows · 제거 미실행",lambda f:grab(wizard,f))
    finally:
        wizard.destroy()


if __name__ == "__main__":
    main()
