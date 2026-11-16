"""Regression guard for the Windows title editor's horizontal scroll UX."""
import ast
from pathlib import Path


def test_title_editor_single_line_list_elides_long_titles_without_horizontal_scroll():
    source = Path(__file__).resolve().parents[1].joinpath('src/playdock/ui/editor_layout.py').read_text(encoding='utf-8')
    root = ast.parse(source)
    # Check the configuration of the actual left-hand game list, not other dialogs.
    make_ui = next(node for node in root.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'build_title_editor_ui')
    calls = [node for node in ast.walk(make_ui) if isinstance(node, ast.Call)]

    def configured(method, tail):
        return any(isinstance(c.func, ast.Attribute)
                   and c.func.attr == method
                   and isinstance(c.func.value, ast.Attribute)
                   and c.func.value.attr == 'games_list'
                   and c.args and ast.unparse(c.args[0]).endswith(tail)
                   for c in calls)

    assert configured('setHorizontalScrollBarPolicy', 'ScrollBarAlwaysOff')
    assert configured('setTextElideMode', 'ElideRight')
    assert configured('setWordWrap', 'False')


def test_game_item_still_uses_full_title_in_model():
    source = Path(__file__).resolve().parents[1].joinpath('src/playdock/controllers/title_editor.py').read_text(encoding='utf-8')
    root = ast.parse(source)
    pop = next(node for node in ast.walk(root)
               if isinstance(node, ast.FunctionDef) and node.name == 'populate'
               and any(isinstance(n, ast.Attribute) and n.attr == 'games_list' for n in ast.walk(node)))
    assert any(isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name)
               and node.func.id == 'QListWidgetItem'
               and node.args and isinstance(node.args[0], ast.Name)
               and node.args[0].id == 'title'
               for node in ast.walk(pop))
