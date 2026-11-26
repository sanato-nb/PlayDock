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


def test_game_management_functions_and_settings_order(
        app, tmp_path, monkeypatch):
    window, _, game = make_window(tmp_path, monkeypatch)
    try:
        window.populate_games(game.id)
        manual = capture_menu(window.extra_menu_btn).actions()
        assert [a.text() for a in manual] == [
            "게임 이름 변경 (수동)",
            "작품 코드 설정",
            "배너·아이콘 수동 설정",
            "공식 배너·아이콘 적용",
            "실행 옵션 설정",
            "공식 작품 페이지 열기",
        ]
        subitems = manual[2].menu().actions()
        assert [a.text() for a in subitems] == [
            "배너 이미지 선택", "아이콘 이미지 선택",
        ]
        assert all(manual[i].isEnabled() for i in (0, 1, 2))
        assert not manual[3].isEnabled()  # no official image
        assert not manual[4].isEnabled()  # not installed
        assert not manual[5].isEnabled()  # no confirmed URL

        settings = [x.text() for x in capture_menu(window.settings_menu_btn).actions()
                    if not x.isSeparator()]
        assert settings == [
            "폴더 설정", "데이터 관리", "라이브러리 속성",
            "DB 상태 확인", "개발자 후원 버튼 표시",
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
    import ast
    sections = {node.name: ast.get_source_segment(layout, node)
                for node in ast.parse(layout).body if isinstance(node, ast.FunctionDef)}
    top = sections["_build_top_bar"]
    detail = "\n".join(body for name, body in sections.items() if name != "_build_top_bar")
    main = sections["build_main_ui"]
    assert main.index("_build_top_bar(") < main.index("_build_game_details(")
    assert "_build_sidebar(" in main
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
    # Hover tooltips are intentionally disabled; preserve accessible control names.
    assert back.toolTip() == ""
    assert back.accessibleName() == "뒤로"
    assert not back.icon().isNull()
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


def test_sidebar_rebuild_reuses_icons_and_collection_snapshot(app, tmp_path, monkeypatch):
    from controllers import library as controller
    window, _, game = make_window(tmp_path, monkeypatch)
    try:
        ids = {window.collections.create(name) for name in ("A", "B", "C")}
        window.collections.set_game_memberships(game.id, ids)
        monkeypatch.setattr(window, "present_game", lambda: None)
        original_list = window.collections.list
        original_icon = controller.game_art_icon
        list_calls = []
        icon_calls = []

        def counted_list():
            list_calls.append(True)
            return original_list()

        def counted_icon(path, fallback):
            icon_calls.append(path)
            return original_icon(path, fallback)

        monkeypatch.setattr(window.collections, "list", counted_list)
        monkeypatch.setattr(controller, "game_art_icon", counted_icon)
        for rebuild in range(1, 3):
            window.populate_games(game.id)
            assert len(list_calls) == rebuild
            assert len(icon_calls) == rebuild
            groups = [window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())]
            rows = [group.child(0) for group in groups if group.childCount()]
            assert len(rows) == 3
            assert all(window.tree_identity(row) == ("game", game.id) for row in rows)
            assert all(not row.icon(0).isNull() for row in rows)
            assert window.selected_id == game.id
    finally:
        window.close()


def test_detail_refresh_shares_selected_metadata_and_verified_db_snapshot(app, tmp_path, monkeypatch):
    from controllers import library as controller
    window, lib, game = make_window(tmp_path, monkeypatch)
    try:
        window.work_db._upsert_verified([{
            "store": "dlsite", "code": "RJ123456", "title": "Verified title",
            "page_url": PAGE,
        }])
        assert window.work_db.save_verified_game_link(game.id, "dlsite", "RJ123456")
        lib.update_meta(game, artwork_source="Test source")
        window.populate_games(game.id)
        monkeypatch.setattr(controller, "discover_local", lambda *_: [])
        original_meta = lib.meta
        original_batch = window.work_db.get_linked_official_works
        original_single = window.work_db.get_linked_official_work
        calls = {"meta": 0, "batch": 0, "single": 0}

        def meta(item):
            calls["meta"] += 1
            return original_meta(item)

        def batch(ids):
            calls["batch"] += 1
            return original_batch(ids)

        def single(game_id):
            calls["single"] += 1
            return original_single(game_id)

        monkeypatch.setattr(lib, "meta", meta)
        monkeypatch.setattr(window.work_db, "get_linked_official_works", batch)
        monkeypatch.setattr(window.work_db, "get_linked_official_work", single)
        window.present_game()
        assert calls == {"meta": 1, "batch": 1, "single": 0}
        assert "Verified title" in window.game_info.text()
        assert "Test source" in window.game_info.text()
        assert window.function_menu_btn.isEnabled()
        lib.update_meta(game, product_code="")
        calls.update(meta=0, batch=0, single=0)
        window.present_game()
        assert calls == {"meta": 1, "batch": 1, "single": 0}
        assert "Verified title" not in window.game_info.text()
        assert not window.function_menu_btn.isEnabled()
    finally:
        window.close()


def test_support_button_opens_only_on_click_and_handles_failure(app, tmp_path, monkeypatch):
    from controllers import window_actions
    calls = []
    messages = []
    monkeypatch.setattr(window_actions.webbrowser, "open", lambda url: calls.append(url) or True)
    monkeypatch.setattr(window_actions, "show_message", lambda *args: messages.append(args))
    window, _, _ = make_window(tmp_path, monkeypatch)
    try:
        assert not calls
        actions = capture_menu(window.settings_menu_btn).actions()
        assert not calls
        assert actions[-1].text() == "개발자 후원 버튼 표시"
        assert actions[-1].isCheckable() and actions[-1].isChecked()
        support = window.support_btn
        assert support.text() == "개발자 후원" and support.isEnabled()
        assert support.parentWidget() is window.settings_menu_btn.parentWidget()
        assert support.parentWidget().layout().itemAt(support.parentWidget().layout().count()-2).widget() is support
        window.show()
        for width, height in ((950, 620), (1380, 840)):
            window.resize(width, height)
            app.processEvents()
            assert support.isVisible()
            assert support.geometry().right() < window.settings_menu_btn.geometry().left()
            assert support.geometry().right() < support.parentWidget().width()
        assert not calls
        support.click()
        assert calls == ["https://fairy.hada.io/@playdock"]
        assert not messages
        monkeypatch.setattr(window_actions.webbrowser, "open", lambda url: False)
        support.click()
        assert messages == [(window, "브라우저 실행 실패", "https://fairy.hada.io/@playdock")]
    finally:
        window.close()

    
def test_support_visibility_persists_and_install_button_is_blue(app, tmp_path, monkeypatch):
    import app as launcher
    window, lib, game = make_window(tmp_path, monkeypatch)
    try:
        window.populate_games(game.id)
        assert "#237cb2" in window.main_button.styleSheet()
        window.show()
        app.processEvents()
        assert window.support_btn.isVisible()
        original = dict(lib.settings)
        action = capture_menu(window.settings_menu_btn).actions()[-1]
        assert action.isChecked()
        action.trigger()
        assert window.support_btn.isHidden()
        reopened = Library(lib.store)
        assert reopened.settings == {**original, "show_support_button": False}
        monkeypatch.setattr(launcher, "Library", lambda: reopened)
        second = launcher.MainWindow()
        try:
            second.show()
            app.processEvents()
            assert second.support_btn.isHidden()
            action = capture_menu(second.settings_menu_btn).actions()[-1]
            assert not action.isChecked()
            action.trigger()
            assert second.support_btn.isVisible()
            assert Library(lib.store).settings["show_support_button"] is True
        finally:
            second.close()
    finally:
        window.close()
