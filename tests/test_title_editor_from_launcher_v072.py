"""Legacy launcher tests updated: the title editor runs inside PlayDock.exe."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_launcher_opens_single_game_editor_in_process():
    metadata = read("src/playdock/controllers/metadata.py")
    tree = ast.parse(metadata)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "open_title_editor" in funcs
    assert "open_bulk_name_settings" in funcs
    assert "title_editor_closed" in funcs
    assert "from title_editor import TitleEditor" in metadata
    assert "subprocess.Popen([program" not in metadata
    assert "single_game_only=True" in metadata
    assert "editor.closed.connect(self.title_editor_closed)" in metadata


def test_title_editor_initial_game_is_filtered_to_one():
    code = read("title_editor.py")
    logic = read("src/playdock/controllers/title_editor.py")
    assert "self.selected_id: str | None = initial_game_id" in code
    assert "self.single_game_only = bool(single_game_only)" in code
    assert "if self.single_game_only else all_games" in logic
    assert "if keep == game.id:" in logic
    assert "self.closed.emit()" in logic
    assert "self.bulk_settings_btn.hide()" in code


def test_top_bar_uses_bulk_selection_dialog_directly():
    layout = read("src/playdock/ui/launcher_layout.py")
    metadata = read("src/playdock/controllers/metadata.py")
    menus = read("src/playdock/controllers/window_actions.py")
    context = read("src/playdock/controllers/library.py")
    assert '("이름 설정", self.open_bulk_name_settings)' in layout
    assert "BulkTitleSettingsDialog(self.library, self.games, None, self)" in metadata
    assert "여러 게임 이름 설정..." in menus
    assert "이 게임 이름 설정..." in context


def test_setup_has_no_second_name_editor_binary_requirement():
    setup = read("setup_wizard.py")
    builder = read("scripts/build_setup_windows.bat")
    assert "payload_title_editor()" not in setup
    assert '--add-binary "dist\\PlayDock_TitleEditor.exe;payload"' not in builder
    assert '--name "PlayDock_TitleEditor"' not in builder
