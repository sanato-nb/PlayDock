from refactor_test_support import launcher_source, editor_source
"""Cross-platform checks for the native title bar integration.

UI rendering itself must still be checked on Windows 10/11 with PySide6.
"""
from pathlib import Path
_ui_main = launcher_source()


import ctypes
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
WIZARD = (ROOT / 'setup_wizard.py').read_text(encoding='utf-8')
BUILD = (ROOT / 'scripts/build_setup_windows.bat').read_text(encoding='utf-8')
spec = importlib.util.spec_from_file_location('native_caption', ROOT / 'src/playdock/native_caption.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def test_all_qt_dialogs_have_global_titlebar_filter():
    assert 'class DarkCaptionEventFilter(QObject)' in APP
    assert 'QEvent.Type.Show' in APP
    assert 'QEvent.Type.WinIdChange' in APP
    assert 'isinstance(watched, (QMainWindow, QDialog))' in APP
    assert 'app.installEventFilter(caption_filter)' in APP
    assert APP.index('app.installEventFilter(caption_filter)') < APP.index('if not library.config_path.is_file()')


def test_file_dialogs_are_qt_themed_instead_of_native_windows():
    assert APP.count('QFileDialog.getExistingDirectory(') >= 1
    assert APP.count('QFileDialog.getOpenFileName(') >= 3
    assert APP.count('QFileDialog.getSaveFileName(') == 1
    assert APP.count('QFileDialog.Option.DontUseNativeDialog') >= 5


def test_windows_titlebar_keeps_native_window_frame():
    assert 'class ThemedDialog(QDialog)' in APP
    assert 'Qt.WindowType.FramelessWindowHint' in APP  # custom dialogs and file chooser only
    main_class = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8').split('class MainWindow(', 1)[1]
    assert 'FramelessWindowHint' not in main_class
    assert 'DwmSetWindowAttribute' in (ROOT / 'src/playdock/native_caption.py').read_text(encoding='utf-8')
    if native.sys.platform != 'win32':
        assert native.windows_dark_caption(1234) is False


def test_dwm_fallback_and_colors(monkeypatch):
    class FakeFunction:
        def __init__(self):
            self.calls = []
        def __call__(self, hwnd, attr, ptr, length):
            self.calls.append(attr)
            return 1 if attr == 20 else 0

    call = FakeFunction()
    class FakeDLL:
        DwmSetWindowAttribute = call
    monkeypatch.setattr(native.sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *_args, **_kwargs: FakeDLL(), raising=False)
    assert native.windows_dark_caption(1234)
    assert call.calls == [20, 19, 35, 36]


def test_setup_wizard_titlebar_includes_shared_style():
    assert 'from native_caption import darken_tk_root' in WIZARD
    assert 'self.after(0, lambda: darken_tk_root(self))' in WIZARD
    assert 'setup_wizard.py' in BUILD


def test_file_chooser_has_own_dark_caption_and_retains_native_qt_selection(monkeypatch, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
    from ui.dialogs.file_dialog import PlayDockFileDialog
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    image = tmp_path / "test.png"
    image.write_bytes(b"fixture")
    dialog = PlayDockFileDialog(None, "이미지 선택", str(tmp_path), "이미지 (*.png)")
    try:
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog._caption_title.text() == "이미지 선택"
        assert "#111923" in dialog._caption.styleSheet()
        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
        assert dialog.nameFilters() == ["이미지 (*.png)"]
        assert not dialog.isSizeGripEnabled()
        dialog.selectFile(str(image))
        assert Path(dialog.selectedFiles()[0]) == image
        assert dialog.layout().contentsMargins().top() >= 34
        dialog.show()
        app.processEvents()
        dialog.resize(920, 620)
        app.processEvents()
        assert dialog._caption.width() == dialog.width() - 8
        dialog._caption_close.click()
        assert dialog.result() == QDialog.DialogCode.Rejected
    finally:
        dialog.close()


def test_file_chooser_save_and_directory_wrappers(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
    from ui.dialogs.file_dialog import PlayDockFileDialog
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    seen = []
    def accept_fake(dialog):
        seen.append((dialog.fileMode(), dialog.acceptMode(), dialog.selectedFiles()))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PlayDockFileDialog, "exec", accept_fake)
    destination = tmp_path / "report.txt"
    saved, selected_filter = PlayDockFileDialog.getSaveFileName(
        None, "TXT 저장", str(destination), "텍스트 (*.txt)")
    assert Path(saved) == destination
    assert selected_filter == "텍스트 (*.txt)"
    folder = PlayDockFileDialog.getExistingDirectory(None, "폴더 선택", str(tmp_path))
    assert Path(folder) == tmp_path
    assert seen[0][:2] == (QFileDialog.FileMode.AnyFile, QFileDialog.AcceptMode.AcceptSave)
    assert seen[1][0] == QFileDialog.FileMode.Directory
    monkeypatch.setattr(PlayDockFileDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert PlayDockFileDialog.getOpenFileName(None, "취소", str(tmp_path)) == ("", "")
