from refactor_test_support import launcher_source, editor_source
"""Regression coverage for the Windows white-dropdown/white-text issue.

Qt cannot run in the Linux test image in all build environments, so also keep
source assertions. Integration tests run on Windows when PySide6 is installed.
"""
from pathlib import Path
_ui_main = launcher_source()


import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
TITLE = (ROOT / 'src/playdock/ui/dialogs/title.py').read_text(encoding='utf-8')
SELECTOR = (ROOT / 'src/playdock/ui/selectors.py').read_text(encoding='utf-8')


def test_game_exe_selector_uses_dark_menu_and_ai_settings_removed():
    assert 'self.combo = DarkMenuSelect()' in APP
    assert 'self.provider = QComboBox()' not in APP
    assert 'class SettingsDialog(' not in APP


def test_current_title_selectors_are_dark():
    for name in ('mode', 'language', 'scope'):
        assert f'self.{name} = DarkMenuSelect()' in TITLE


def test_menu_popup_has_explicit_dark_background_and_light_text():
    assert 'menu.setStyleSheet(DARK_POPUP_STYLE)' in SELECTOR
    styles = (ROOT / 'src/playdock/ui/styles.py').read_text(encoding='utf-8')
    import ast
    popup = next(ast.literal_eval(node.value) for node in ast.parse(styles).body
                 if isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == 'DARK_POPUP_STYLE'
                     for target in node.targets))
    assert 'QMenu::item:selected' in popup
    assert 'background-color:#242428' in popup
    assert 'color:#f1eff4' in popup
    assert 'from ui.styles import DARK_POPUP_STYLE' in SELECTOR
    assert 'menu.popup(' in SELECTOR
    assert 'self._menu_open' in SELECTOR


def test_dark_selector_keeps_selection_api():
    for name in ('addItem', 'findData', 'currentData', 'currentText', 'setCurrentIndex'):
        assert f'def {name}(' in SELECTOR


def test_select_widget_can_be_used_in_offscreen_qt_when_available():
    """Exercise actual Qt signal and menu styling where PySide6 is present."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip('PySide6 not installed in this test environment')
    script = r'''
from PySide6.QtWidgets import QApplication
from ui.selectors import DarkMenuSelect
app = QApplication([])
s = DarkMenuSelect()
events = []
s.currentIndexChanged.connect(events.append)
s.addItem('OpenAI', 'openai')
s.addItem('Google Gemini', 'gemini')
s.addItem('Anthropic Claude', 'anthropic')
assert s.findData('gemini') == 1
s.setCurrentIndex(1)
assert s.currentData() == 'gemini'
assert s.currentText() == 'Google Gemini'
assert events[-1] == 1
s.resize(300, 40)
s.show()
s._show_menu()
assert s._menu is not None
assert 'background-color:#242428' in s._menu.styleSheet()
assert 'color:#f1eff4' in s._menu.styleSheet()
s._menu.close()
app.processEvents()
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    subprocess.run([sys.executable, '-c', script], cwd=str(ROOT), env=env, check=True, timeout=25)
