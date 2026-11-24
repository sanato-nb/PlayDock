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
    for name in ('open_filter_menu', 'show_image_menu'):
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
    assert 'if self.is_menu_open():' in APP
    assert 'path.lineTo(arrow_x, arrow_y - 3)' in APP
    assert 'path.lineTo(cx, cy - 2.5)' in APP
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
    assert 'self.change_image("hero")' in body_of('show_image_menu')
    assert 'self.change_image("icon")' in body_of('show_image_menu')
    assert 'self.refresh_local_art()' in body_of('show_image_menu')
    assert 'self.fetch_art()' not in body_of('show_image_menu')
    # All title editing was deliberately moved to title_editor.py.
    assert 'def show_game_menu(' not in APP
    assert 'self.rename_game()' not in APP
    assert 'self.rename_collection()' in body_of('sidebar_context_menu')
    assert 'self.delete_collection()' in body_of('sidebar_context_menu')
