from refactor_test_support import launcher_source, editor_source
"""Code-structure regressions for interactive dropdown and vector ellipsis.

Pure static checks: real Qt mouse interaction still requires Windows GUI QA.
"""
import ast

from pathlib import Path
_ui_main = launcher_source()

APP = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
TREE = ast.parse(APP)


def body_of(method):
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method:
            return ast.get_source_segment(APP, node)
    raise AssertionError(f'missing {method}')


def test_all_dropdowns_use_async_popups_not_blocking_exec():
    for name in ('open_filter_menu', 'show_extra_menu', 'show_function_menu'):
        body = body_of(name)
        assert '.present_popup(' in body, name
        assert '.exec(' not in body, name
    body = body_of('present_popup')
    assert 'menu.popup(' in body
    assert 'menu.aboutToHide.connect(finished)' in body
    assert 'self._popup_menu.close()' in body
    assert "self._menu_open = False" in body


def test_arrow_points_up_when_open_for_filter_and_image_more_buttons():
    assert 'class LibraryFilterButton(PopupMenuState, QPushButton)' in APP
    assert 'class ChevronMenuButton(PopupMenuState, QPushButton)' in APP
    assert 'draw_menu_chevron(painter, arrow_x, arrow_y, expanded=self.is_menu_open(), half_width=5, tip_height=3)' in APP
    assert 'draw_menu_chevron(painter, cx, cy, expanded=self.is_menu_open(), half_width=4.5, tip_height=2.5)' in APP
    # Verify the shared implementation rather than requiring duplicated paths.
    selector = (Path(__file__).resolve().parents[1] / 'src/playdock/ui/selectors.py').read_text('utf-8')
    helper = next(node for node in ast.parse(selector).body
                  if isinstance(node, ast.FunctionDef) and node.name == 'draw_menu_chevron')

    class RecordingPath:
        def __init__(self):
            self.points = []
        def moveTo(self, x, y):
            self.points.append((x, y))
        def lineTo(self, x, y):
            self.points.append((x, y))

    class Painter:
        def drawPath(self, path):
            self.points = path.points

    ns = {'QPainterPath': RecordingPath}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<chevron>', 'exec'), ns)
    for half_width, tip_height in ((5, 3), (4.5, 2.5)):
        for expanded in (True, False):
            painter = Painter()
            ns['draw_menu_chevron'](painter, 20, 10, expanded=expanded,
                                    half_width=half_width, tip_height=tip_height)
            sign = 1 if expanded else -1
            assert painter.points == [(20 - half_width, 10 + sign * 2),
                                      (20, 10 - sign * tip_height),
                                      (20 + half_width, 10 + sign * 2)]
    assert 'menu.aboutToHide.connect(finished)' in APP


def test_sidebar_ellipsis_removed_and_collection_context_menu_retained():
    assert 'manage_btn = EllipsisButton()' not in APP
    assert 'def collection_menu(self):' not in APP
    assert 'self.tree.customContextMenuRequested.connect(self.sidebar_context_menu)' in APP
    assert "menu.addAction('모음집 이름 변경')" in body_of('sidebar_context_menu')
    assert "menu.addAction('모음집 삭제')" in body_of('sidebar_context_menu')


def test_mode_filter_still_emits_selection_changes():
    assert 'self.currentIndexChanged.emit(index)' in body_of('setCurrentIndex')
    assert 'self.mode_filter.currentIndexChanged.connect(self.populate_games)' in APP


def test_popup_actions_still_connected_to_business_functions():
    assert 'self.change_image("hero")' in body_of('show_extra_menu')
    assert 'self.change_image("icon")' in body_of('show_extra_menu')
    assert 'self.open_bulk_official_artwork' in body_of('show_function_menu')
    assert 'self.identify_selected_game' in body_of('show_extra_menu')
    assert 'self.fetch_art()' not in body_of('show_extra_menu')
    assert 'self.rename_selected_game' in body_of('show_extra_menu')
    assert 'def show_game_menu(' not in APP
    assert 'self.rename_game()' not in APP
    assert 'self.rename_collection()' in body_of('sidebar_context_menu')
    assert 'self.delete_collection()' in body_of('sidebar_context_menu')


def test_collection_chevrons_use_qt_owned_cache_and_keep_pixels():
    import os
    import subprocess
    import sys
    import pytest
    pytest.importorskip("PySide6")
    script = r'''
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmapCache
from PySide6.QtCore import QSize
from ui.widgets.launcher import collection_chevron, _render_collection_chevron
app = QApplication([])
for expanded in (False, True):
    first = collection_chevron(expanded).pixmap(QSize(20, 20), 2.0).toImage()
    expected = _render_collection_chevron(expanded).toImage()
    assert not first.isNull()
    assert first == expected
    assert collection_chevron(expanded).pixmap(QSize(20, 20), 2.0).toImage() == first
    QPixmapCache.clear()
    assert collection_chevron(expanded).pixmap(QSize(20, 20), 2.0).toImage() == first
assert collection_chevron(False).pixmap(QSize(20, 20), 2.0).toImage() != collection_chevron(True).pixmap(QSize(20, 20), 2.0).toImage()
QPixmapCache.clear()
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    subprocess.run([sys.executable, '-c', script], env=env, check=True, timeout=25)
