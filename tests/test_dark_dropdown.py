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


def test_ai_provider_and_game_exe_selector_do_not_use_native_combo():
    assert 'self.provider = DarkMenuSelect()' in APP
    assert 'self.combo = DarkMenuSelect()' in APP
    assert 'self.provider = QComboBox()' not in APP
    assert 'form.addRow("AI 서비스", self.provider)' in APP


def test_current_title_selectors_are_dark():
    for name in ('mode', 'language', 'scope'):
        assert f'self.{name} = DarkMenuSelect()' in TITLE


def test_menu_popup_has_explicit_dark_background_and_light_text():
    assert 'menu.setStyleSheet(DARK_POPUP_STYLE)' in SELECTOR
    assert 'QMenu::item:selected' in SELECTOR
    assert 'background-color:#182a3b' in SELECTOR
    assert 'color:#ecf4fc' in SELECTOR
    assert 'menu.popup(' in SELECTOR
    assert 'self._menu_open' in SELECTOR


def test_previous_selected_api_provider_is_retained():
    assert 'self.provider.findData(provider_id)' in APP
    assert 'self.provider.currentData() or "openai"' in APP
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
assert 'background-color:#182a3b' in s._menu.styleSheet()
assert 'color:#ecf4fc' in s._menu.styleSheet()
s._menu.close()
app.processEvents()
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    subprocess.run([sys.executable, '-c', script], cwd=str(ROOT), env=env, check=True, timeout=25)
