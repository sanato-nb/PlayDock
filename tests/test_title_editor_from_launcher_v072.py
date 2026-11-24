from refactor_test_support import launcher_source, editor_source
"""Regression tests for opening the standalone name editor from the launcher."""
from pathlib import Path
_ui_main = launcher_source()
_ui_editor = editor_source()


import ast
import pytest

from title_editor_entry import EDITOR_EXE, title_editor_command

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_app_uses_sibling_title_editor_and_selected_game(tmp_path):
    install = tmp_path / 'Local Game Shelf'
    install.mkdir()
    (install / EDITOR_EXE).write_bytes(b'exe-placeholder')
    launcher = install / 'PlayDock.exe'
    program, argv, cwd = title_editor_command(executable=launcher, frozen=True,
                                               game_id='9fc456_abc')
    assert program == str(install / EDITOR_EXE)
    assert argv == ['--game-id', '9fc456_abc']
    assert cwd == str(install)


def test_no_selected_game_opens_editor_without_selection_argument(tmp_path):
    (tmp_path / EDITOR_EXE).write_bytes(b'exe-placeholder')
    program, args, cwd = title_editor_command(executable=tmp_path / 'PlayDock.exe',
                                               frozen=True)
    assert program.endswith(EDITOR_EXE)
    assert args == []


def test_missing_editor_is_reported_instead_of_launching_main_exe(tmp_path):
    with pytest.raises(FileNotFoundError, match='이름 관리자'):
        title_editor_command(executable=tmp_path / 'PlayDock.exe', frozen=True)


def test_source_mode_uses_python_and_independent_editor_script(tmp_path):
    (tmp_path / 'title_editor.py').write_text('print(1)', encoding='utf-8')
    python = Path('/fake/python.exe')
    program, argv, cwd = title_editor_command(executable=python, frozen=False,
                                               source_dir=tmp_path, game_id='12345')
    assert program == str(python)
    assert argv == [str(tmp_path / 'title_editor.py'), '--game-id', '12345']
    assert cwd == str(tmp_path)


def test_game_id_passed_as_one_argument_not_as_shell_command(tmp_path):
    (tmp_path / EDITOR_EXE).write_bytes(b'exe-placeholder')
    suspicious = 'abc && del data'
    _, argv, _ = title_editor_command(executable=tmp_path / 'PlayDock.exe',
                                       frozen=True, game_id=suspicious)
    assert argv == ['--game-id', suspicious]


def test_main_launcher_has_entry_in_both_context_menus_and_refresh_after_exit():
    app = (ROOT / 'app.py').read_text(encoding='utf-8') + _ui_main
    tree = ast.parse(app)
    cls = next(c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'MainWindow')
    methods = {m.name: m for m in ast.walk(tree) if isinstance(m, ast.FunctionDef)}
    assert {'open_title_editor', 'title_editor_check_finished', 'show_extra_menu',
            'sidebar_context_menu'} <= methods.keys()
    assert '게임 이름 수정 / 이름 관리자 열기' in app
    assert "menu.addAction('게임 이름 수정...')" in app
    start = ast.get_source_segment(app, methods['open_title_editor'])
    finished = ast.get_source_segment(app, methods['title_editor_check_finished'])
    assert 'game.id' in start
    assert 'subprocess.Popen([program, *arguments]' in start
    assert 'self.reload(prefer_id=selected_id)' in finished


def test_editor_uses_requested_game_id_before_initial_list_population():
    editor = (ROOT / 'title_editor.py').read_text(encoding='utf-8') + _ui_editor
    assert 'parser.add_argument(\'--game-id\'' in editor
    assert 'TitleEditor(initial_game_id=args.game_id)' in editor
    assert 'self.selected_id: str | None = initial_game_id' in editor
    assert 'if keep == game.id:' in editor


def test_installer_still_includes_editor_executable():
    script = (ROOT / 'scripts/Build-Windows-Release.ps1').read_text(encoding='utf-8-sig')
    assert "Run-PyInstaller 'PlayDock_TitleEditor'" in script
    assert "'dist\\PlayDock_TitleEditor.exe;payload'" in script
