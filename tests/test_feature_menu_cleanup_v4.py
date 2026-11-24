"""Top '기능', lower '게임 관리', trimmed Settings, and DB-only artwork safety.

No real websites, archive renames, credentials, or user data.
"""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from core import Library
from database.work_repository import WorkDatabase
from integrations.official_lookup.code_only import Work
from workers.identity_artwork import IdentityArtworkThread
from ui.widgets.launcher import ChevronMenuButton
from controllers.window_actions import WindowActionControllerMixin


PAGE = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
ART = "https://img.dlsite.jp/cover.jpg"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def make_window(tmp_path, monkeypatch):
    import app as application
    source = tmp_path / "archives"
    install = tmp_path / "installed"
    source.mkdir()
    install.mkdir()
    (source / "Example No ID.7z").write_bytes(b"do not modify this archive")
    lib = Library(tmp_path / "data")
    lib.settings["archives"] = str(source)
    lib.settings["library"] = str(install)
    monkeypatch.setattr(application, "Library", lambda: lib)
    window = application.MainWindow()
    return window, lib, next(g for g in window.games if g.archive)


def capture_menu(button):
    menus = []
    button.present_popup = lambda menu, **kwargs: menus.append(menu)
    button.click()
    assert menus
    return menus[-1]


def test_top_function_menu_disabled_until_official_link_and_image_candidate(
        app, tmp_path, monkeypatch):
    window, lib, game = make_window(tmp_path, monkeypatch)
    try:
        window.populate_games(game.id)
        assert window.extra_menu_btn.text() == "게임 관리"
        assert window.function_menu_btn.text() == "기능"
        assert window.catalog_collection_btn.text() == "게임 정보 수집"
        assert "게임 이름 변경" not in capture_menu(window.settings_menu_btn).actions()[0].text()

        assert not window.function_menu_btn.isEnabled()
        menus = []
        window.function_menu_btn.present_popup = lambda menu, **kwargs: menus.append(menu)
        window.function_menu_btn.click()
        assert not menus
        # Inspect the same QAction predicates directly without clicking a disabled button.
        window.show_function_menu()
        menu = menus[-1]
        image, names = menu.actions()
        assert "공식 배너·아이콘" in image.text()
        assert not image.isEnabled()
        assert not names.isEnabled()

        window.work_db._upsert_verified([{
            "store": "dlsite", "code": "RJ123456",
            "title": "Game from works DB", "page_url": PAGE,
        }])
        assert window.work_db.save_verified_game_link(game.id, "dlsite", "RJ123456")
        window.catalog_collection_finished()
        assert window.function_menu_btn.isEnabled()
        menu = capture_menu(window.function_menu_btn)
        assert not menu.actions()[0].isEnabled()  # link alone is insufficient
        assert menu.actions()[1].isEnabled()  # official game name available

        assert window.work_db.save_official_image_urls(
            "dlsite", "RJ123456", {"hero": ART}) == 1
        menu = capture_menu(window.function_menu_btn)
        assert menu.actions()[0].isEnabled()
        assert menu.actions()[1].isEnabled()
        window.reload(prefer_id=game.id)
        assert capture_menu(window.function_menu_btn).actions()[0].isEnabled()
        assert (tmp_path / "archives" / "Example No ID.7z").read_bytes() == b"do not modify this archive"
    finally:
        window.close()


def test_game_management_functions_and_only_four_settings(
        app, tmp_path, monkeypatch):
    window, _, game = make_window(tmp_path, monkeypatch)
    try:
        window.populate_games(game.id)
        manual = capture_menu(window.extra_menu_btn).actions()
        assert [a.text() for a in manual] == [
            "게임 이름 변경 (수동)",
            "배너·아이콘 수동 설정",
            "공식 배너·아이콘 적용",
            "실행 옵션 설정",
            "공식 작품 페이지 열기",
        ]
        subitems = manual[1].menu().actions()
        assert [a.text() for a in subitems] == [
            "배너 이미지 선택", "아이콘 이미지 선택",
        ]
        assert manual[0].isEnabled() and manual[1].isEnabled()
        assert not manual[2].isEnabled()  # no official image
        assert not manual[3].isEnabled()  # not installed
        assert not manual[4].isEnabled()  # no confirmed URL

        settings = [x.text() for x in capture_menu(window.settings_menu_btn).actions()
                    if not x.isSeparator()]
        assert settings == [
            "폴더 설정", "데이터 관리", "라이브러리 속성",
            "DB 상태 확인",
        ]
        assert not any("AI" in a or "이름 설정" in a or "이미지" in a
                       for a in settings)
        assert not window.function_menu_btn.isEnabled()
        assert all(not a.text().endswith(("...", "…")) for a in manual + subitems)
    finally:
        window.close()


def test_image_worker_uses_verified_game_link_even_if_filename_has_no_code(
        app, tmp_path, monkeypatch):
    from workers import identity_artwork as module
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([{
        "store": "dlsite", "code": "RJ123456",
        "title": "Confirmed", "page_url": PAGE,
    }])
    db.save_official_image_urls("dlsite", "RJ123456", {"hero": ART})
    work = Work("RJ123456", "Confirmed", "maniax", PAGE, "verified", "dlsite")

    def cannot_search(*args, **kwargs):
        raise AssertionError("Official image menu must not run game identity scan")
    monkeypatch.setattr(module, "check", cannot_search)
    calls = []

    def fake_prepare(w, *, candidates=None):
        assert w.code == "RJ123456"
        assert candidates == {"hero": ART}
        calls.append(candidates)
        return {"hero": object()}

    monkeypatch.setattr(module, "prepare_official_images", fake_prepare)
    runner = IdentityArtworkThread(
        "Example No ID.7z", db_path=db.path, verified_work=work)
    result, failures = [], []
    runner.complete.connect(lambda *x: result.append(x))
    runner.failed.connect(failures.append)
    runner.run()
    assert not failures
    assert result and result[0][1] == work
    assert set(result[0][2]) == {"hero"}
    assert len(calls) == 1


def test_source_menu_order_and_sidebar_duplicates_removed():
    root = Path(__file__).resolve().parents[1]
    layout = (root / "src/playdock/ui/launcher_layout.py").read_text("utf-8")
    code = (root / "src/playdock/controllers/library.py").read_text("utf-8")
    actions = (root / "src/playdock/controllers/window_actions.py").read_text("utf-8")
    top, detail = layout.split("outer.addWidget(top)", 1)
    assert top.index('"게임 정보 수집"') < top.index('"새로고침"')
    assert top.index('"새로고침"') < top.index("ChevronMenuButton('기능')") < top.index('ChevronMenuButton("설정")')
    assert "ChevronMenuButton('게임 관리')" not in top
    assert "ChevronMenuButton('게임 관리')" in detail
    context = code.split("def sidebar_context_menu", 1)[1].split("def rename_collection", 1)[0]
    assert "세이브 폴더 백업..." not in context
    assert "로컬 이미지 자동 찾기" not in context
    assert "게임 이름 설정..." not in context
    assert "공식 작품 페이지 열기" not in context
    settings = actions.split("def show_settings_menu", 1)[1].split("def show_function_menu", 1)[0]
    assert "AI 설정" not in settings
    assert "게임 이름 설정" not in settings
    assert "내 이미지 보관 폴더 열기" not in settings


def test_top_navigation_follows_visible_screen(app, tmp_path, monkeypatch):
    window, _, game = make_window(tmp_path, monkeypatch)
    try:
        assert window.library_nav_btn.isChecked()
        assert not window.collections_nav_btn.isChecked()
        window.collections_nav_btn.click()
        assert window.main_stack.currentWidget() is window.collections_board
        assert window.collections_nav_btn.isChecked()
        assert not window.library_nav_btn.isChecked()
        window.open_game_from_board(game.id)
        assert window.library_nav_btn.isChecked()
        assert not window.collections_nav_btn.isChecked()
        window.show_collection("__uncategorized__")
        assert window.collections_nav_btn.isChecked()
        window.library_nav_btn.click()
        assert window.main_stack.currentWidget() is window.scroll
        assert window.library_nav_btn.isChecked()
        assert not window.collections_nav_btn.isChecked()
    finally:
        window.close()


def test_shared_file_dialog_style_keeps_filters_and_disables_grip(app, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QToolButton
    from ui.dialogs.file_dialog import style_file_dialog
    dialog = QFileDialog(None, "이미지 선택", str(tmp_path), "이미지 (*.png *.jpg)")
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    original = dialog.nameFilters()
    style_file_dialog(dialog)
    assert dialog.property("playdockFileDialogStyled")
    assert not dialog.isSizeGripEnabled()
    assert dialog.nameFilters() == original
    assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
    assert dialog.labelText(QFileDialog.DialogLabel.Reject) == "취소"
    assert dialog.labelText(QFileDialog.DialogLabel.FileName) == "파일 이름:"
    back = dialog.findChild(QToolButton, "backButton")
    assert back is not None and not back.icon().isNull()
    assert back.toolTip() == "뒤로"
    style_file_dialog(dialog)
    dialog.close()


def test_bulk_artwork_enabled_for_other_game_and_collection_view(app,tmp_path,monkeypatch):
    window, lib, game = make_window(tmp_path, monkeypatch)
    try:
        (tmp_path/"archives"/"Unlinked.zip").write_bytes(b"fixture")
        window.reload()
        other=next(g for g in window.games if g.archive.name=="Unlinked.zip")
        window.work_db._upsert_verified([{"store":"dlsite","code":"RJ123456",
            "title":"Verified","page_url":PAGE}])
        assert window.work_db.save_verified_game_link(game.id,"dlsite","RJ123456")
        window.work_db.save_official_image_urls("dlsite","RJ123456",{"hero":ART})
        window.populate_games(other.id)
        assert window.current().id==other.id
        assert capture_menu(window.function_menu_btn).actions()[0].isEnabled()
        assert not capture_menu(window.extra_menu_btn).actions()[2].isEnabled()
        window.populate_games(game.id)
        assert capture_menu(window.extra_menu_btn).actions()[2].isEnabled()
        window.collections_nav_btn.click()
        assert capture_menu(window.function_menu_btn).actions()[0].isEnabled()
    finally:
        window.close()
