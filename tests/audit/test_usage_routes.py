"""Audit-only Qt route probes against synthetic game data; no network or secrets."""
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from core import Library
import app as launcher


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_active_main_menu_routes(qapp, tmp_path, monkeypatch):
    archive = tmp_path / "archives"
    archive.mkdir()
    installed = tmp_path / "installed"
    installed.mkdir()
    source = archive / "Example.7z"
    source.write_bytes(b"synthetic")
    lib = Library(tmp_path / "data")
    lib.change_archive_root(archive)
    lib.change_root(installed)
    monkeypatch.setattr(launcher, "Library", lambda: lib)
    calls = []
    def spy(name):
        def callback(self, *args, **kwargs):
            calls.append((name, args))
        return callback
    # Only intercept business handlers. The real layout, menu builders,
    # QAction signals, DB-based availability and button clicks stay intact.
    routes = ["collect_library_information", "folder_wizard", "data_manager_dialog",
              "library_info_dialog", "show_database_status", "rename_selected_game",
              "change_image", "edit_launch_options", "open_saved_official_page",
              "identify_selected_game", "open_bulk_official_artwork", "open_official_name_settings",
              "open_title_editor", "open_selected_name_settings",
              "open_bulk_name_settings"]
    for name in routes:
        monkeypatch.setattr(launcher.MainWindow, name, spy(name))
    window = launcher.MainWindow()
    try:
        assert not hasattr(window, 'settings_dialog')
        game = next(g for g in window.games if g.archive)
        window.populate_games(game.id)
        def menu(button):
            out = []
            button.present_popup = lambda obj, **kw: out.append(obj)
            button.click()
            assert len(out) == 1
            return out[0]
        window.catalog_collection_btn.click()
        settings = menu(window.settings_menu_btn)
        for action in settings.actions():
            if not action.isSeparator():
                action.trigger()
        manual = menu(window.extra_menu_btn)
        assert not manual.actions()[2].isEnabled()
        assert not manual.actions()[3].isEnabled()
        assert not manual.actions()[4].isEnabled()
        manual.actions()[0].trigger()
        for action in manual.actions()[1].menu().actions():
            action.trigger()
        assert not window.function_menu_btn.isEnabled()
        page = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
        window.work_db._upsert_verified([{"store":"dlsite","code":"RJ123456","title":"Example","page_url":page}])
        assert window.work_db.save_verified_game_link(game.id, "dlsite", "RJ123456")
        window.work_db.save_official_image_urls("dlsite", "RJ123456", {"hero":"https://img.dlsite.jp/cover.jpg"})
        window.refresh_function_availability()
        assert window.function_menu_btn.isEnabled()
        for action in menu(window.function_menu_btn).actions():
            assert action.isEnabled()
            action.trigger()
        menu(window.extra_menu_btn).actions()[2].trigger()
        menu(window.extra_menu_btn).actions()[4].trigger()
        assert [name for name,_ in calls] == [
            "collect_library_information", "folder_wizard", "data_manager_dialog",
            "library_info_dialog", "show_database_status", "rename_selected_game",
            "change_image", "change_image", "open_bulk_official_artwork",
            "open_official_name_settings", "identify_selected_game", "open_saved_official_page"]
        assert calls[6][1] == ("hero",) and calls[7][1] == ("icon",)
        assert source.read_bytes() == b"synthetic"
        print("MAIN_MENU_ROUTES_VERIFIED", [name for name,_ in calls])
    finally:
        window.close()


def test_legacy_editor_ai_routes_still_exist(qapp, tmp_path, monkeypatch):
    from title_editor import TitleEditor
    # No API execution: only record the actual connected mode argument.
    calls = []
    monkeypatch.setattr(TitleEditor, "start_lookup", lambda self, mode: calls.append(mode))
    archive = tmp_path / "archives"
    archive.mkdir()
    (archive / "Example [RJ123456].zip").write_bytes(b"synthetic")
    lib = Library(tmp_path / "data")
    lib.change_archive_root(archive)
    (tmp_path / "installed").mkdir()
    lib.change_root(tmp_path / "installed")
    editor = TitleEditor(library=lib)
    try:
        # Emit the real button signals to verify connection, independently of
        # current credential / detailed-mode visibility predicates.
        editor.translate_btn.clicked.emit()
        editor.gpt_btn.clicked.emit()
        assert calls == ["translate", "gpt"]
        print("LEGACY_EDITOR_AI_ROUTES_VERIFIED", calls)
    finally:
        editor.close()
