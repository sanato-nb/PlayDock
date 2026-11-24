"""Regression: title editing is inside PlayDock.exe, with single/bulk entrypoints."""
from pathlib import Path
from zipfile import ZipFile

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import Qt

from core import Library
from title_editor import TitleEditor
from ui.dialogs.title import BulkTitleSettingsDialog
from services.bulk_title_service import BulkTitleActions

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def qt_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def example(tmp_path):
    root = tmp_path / "archives"
    root.mkdir()
    a = root / "First [RJ123456].zip"
    b = root / "Second [Steam 1091500].7z"
    a.write_bytes(b"first compressed bytes")
    b.write_bytes(b"second compressed bytes")
    lib = Library(store=tmp_path / "localdata")
    lib.change_archive_root(root)
    installed = tmp_path / "installed"
    installed.mkdir()
    lib.change_root(installed)
    games = lib.scan()
    assert len(games) == 2
    return lib, games, a, b


def test_single_editor_is_in_process_and_cannot_switch_games(qt_app, tmp_path):
    lib, games, a, b = example(tmp_path)
    selected = games[0]
    window = TitleEditor(selected.id, library=lib, single_game_only=True)
    try:
        assert window.library is lib
        assert len(window.games) == 1
        assert window.current_game().id == selected.id
        assert window.games_list.count() == 1
        assert window.bulk_settings_btn.isHidden()
        window.toggle_mode()
        assert window.bulk_btn.isHidden()
        window.toggle_mode()
        window.search.setText("")
        window.refresh()
        assert len(window.games) == 1
        window.simple_edit.setText("선택한 게임")
        window.save_simple_title()
        assert "선택한 게임" in lib.title(selected)
        assert a.read_bytes() == b"first compressed bytes"
        assert b.read_bytes() == b"second compressed bytes"
        closed = []
        window.closed.connect(lambda: closed.append(True))
        window.close()
        assert closed == [True]
    finally:
        window.close()


def test_bulk_dialog_starts_unchecked_then_applies_only_selected_games(qt_app, tmp_path, monkeypatch):
    lib, games, a, b = example(tmp_path)
    dialog = BulkTitleSettingsDialog(lib, games, None)
    try:
        assert dialog.targets.rowCount() == 2
        assert not dialog.selected_games()
        dialog.targets.item(0, 0).setCheckState(Qt.CheckState.Checked)
        dialog.targets.item(1, 0).setCheckState(Qt.CheckState.Checked)
        assert len(dialog.selected_games()) == 2
        dialog.create_preview()
        assert dialog.preview_table.rowCount() == 2
        for i in range(2):
            dialog.preview_table.item(i, 2).setText(f"변경된 이름 {i}")
            dialog.preview_table.item(i, 0).setCheckState(Qt.CheckState.Checked)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        dialog.apply_preview()
        assert "변경된 이름" in lib.title(games[0])
        assert "변경된 이름" in lib.title(games[1])
        backups = list((lib.store / "backups").glob("title_bulk_*.zip"))
        assert len(backups) == 1
        with ZipFile(backups[0]) as z:
            assert "manifest.json" in z.namelist()
        assert a.read_bytes() == b"first compressed bytes"
        assert b.read_bytes() == b"second compressed bytes"
    finally:
        dialog.close()


def test_main_window_entrypoints_are_distinct_and_do_not_spawn_exe(qt_app, tmp_path, monkeypatch):
    import app as launcher

    lib, games, a, b = example(tmp_path)
    monkeypatch.setattr(launcher, "Library", lambda: lib)
    # App main initializes an unrelated WorkDatabase for user data.
    window = launcher.MainWindow()
    try:
        window.reload(prefer_id=games[0].id)
        assert window.current() is not None
        assert window.current().id == games[0].id
        window.open_title_editor()
        editor = window.title_editor_window
        assert isinstance(editor, TitleEditor)
        assert editor.single_game_only
        assert editor.current_game().id == games[0].id
        editor.simple_edit.setText("인게임 화면 이름")
        editor.save_simple_title()
        editor.close()
        assert window.title_editor_window is None
        assert "인게임 화면 이름" in window.library.title(
            next(g for g in window.games if g.id == games[0].id))
        class SpyBulk:
            instances = []
            def __init__(self, library, selected_games, initial_id, parent):
                assert library is lib
                assert {x.id for x in selected_games} == {g.id for g in games}
                assert initial_id is None
                self.instances.append(self)
            def exec(self):
                return QDialog.DialogCode.Rejected
        import controllers.metadata as metadata
        monkeypatch.setattr(metadata, "BulkTitleSettingsDialog", SpyBulk)
        window.open_bulk_name_settings()
        assert len(SpyBulk.instances) == 1
        assert a.read_bytes() == b"first compressed bytes"
        assert b.read_bytes() == b"second compressed bytes"
    finally:
        window.close()


def test_public_installer_does_not_require_editor_companion_exe():
    from make_public_release import EXECUTABLES
    assert "PlayDock.exe" in EXECUTABLES
    assert "PlayDock_TitleEditor.exe" not in EXECUTABLES
    assert "PlayDock_Setup.exe" in EXECUTABLES
    assert "PlayDock_Uninstall.exe" in EXECUTABLES
    setup = (ROOT / "setup_wizard.py").read_text(encoding="utf-8")
    assert "payload_title_editor()" not in setup
    build = (ROOT / "scripts/Build-Windows-Release.ps1").read_text(encoding="utf-8-sig")
    assert "Run-PyInstaller 'PlayDock_TitleEditor'" not in build
    assert "'dist\\PlayDock_TitleEditor.exe;payload'" not in build
    assert "Run-PyInstaller 'PlayDock' 'app.py'" in build
    layout = (ROOT / "src/playdock/ui/launcher_layout.py").read_text(encoding="utf-8")
    assert 'self.settings_menu_btn = ChevronMenuButton("설정")' in layout
    actions = (ROOT / "src/playdock/controllers/window_actions.py").read_text(encoding="utf-8")
    assert '공식 게임명 설정 (여러 게임)' in actions
    assert 'self.open_official_name_settings' in actions
    assert 'AI 설정...' not in actions
    ctrl = (ROOT / "src/playdock/controllers/metadata.py").read_text(encoding="utf-8")
    assert "editor = TitleEditor(game.id, library=self.library, single_game_only=True)" in ctrl
    assert "dialog = BulkTitleSettingsDialog(self.library, self.games, None, self)" in ctrl
    assert "subprocess.Popen" not in ctrl
