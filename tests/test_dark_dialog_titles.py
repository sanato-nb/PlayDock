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
    assert 'Qt.WindowType.FramelessWindowHint' in APP  # only custom small dialogs
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
