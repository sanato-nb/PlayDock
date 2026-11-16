"""Source layout regression tests: no PySide6 or GUI runtime needed."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _classes(filename):
    src = (ROOT / filename).read_text(encoding='utf8')
    return {n.name: n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)}


def _methods(node):
    return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}


def test_launcher_entrypoint_only_bootstraps_and_holds_window_state():
    entry = _classes('app.py')['MainWindow']
    assert 'build_ui' in _methods(entry)
    assert 'install_game' not in _methods(entry)
    assert 'launch_game' not in _methods(entry)
    assert 'populate_games' not in _methods(entry)


def test_editor_entrypoint_delegates_editor_events():
    entry = _classes('title_editor.py')['TitleEditor']
    assert 'make_ui' in _methods(entry)
    assert 'save_title' not in _methods(entry)
    assert 'start_lookup' not in _methods(entry)


def test_ui_action_service_boundaries():
    launcher = (ROOT / 'ui/launcher_layout.py').read_text(encoding='utf8')
    controller = _classes('controllers/game_actions.py')['GameActionControllerMixin']
    workers = _classes('services/workers.py')
    assert 'self.action_button("설치", self.main_action)' in launcher or 'self.main_action' in launcher
    assert {'install_game','uninstall_game','launch_game'} <= _methods(controller)
    assert {'InstallThread','UninstallThread','SaveBackupThread'} <= workers.keys()
    assert 'install(self.game,' in (ROOT / 'services/workers.py').read_text(encoding='utf8')


def test_ui_does_not_import_controllers_or_install_service_directly():
    for path in (ROOT / 'ui').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('controllers.'), path
    assert 'from controllers.title_editor import TitleEditorActionsMixin' in (ROOT/'title_editor.py').read_text(encoding='utf8')


def test_no_private_catalog_database_in_source():
    assert not (ROOT/'data').exists()
    for suffix in ('*.db','*.sqlite','*.sqlite3'):
        assert list(ROOT.rglob(suffix)) == []
