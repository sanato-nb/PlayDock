from refactor_test_support import launcher_source, editor_source

from pathlib import Path
_ui_main = launcher_source()


from core import Library
from library_tree import make_sidebar_groups


def test_game_only_no_classifier_and_all_records_visible(tmp_path):
    root = tmp_path / 'installed'
    archive_root = tmp_path / 'archives'
    root.mkdir()
    archive_root.mkdir()
    lib = Library(tmp_path / 'profile')
    lib.change_root(root)
    lib.change_archive_root(archive_root)
    for name in ['Regular Game.zip', 'Korean patch DLC.zip']:
        (archive_root / name).write_bytes(b'not parsed during scan')
    games = lib.scan()
    assert len(games) == 2
    assert all(lib.kind(game) == '게임' for game in games)
    groups = make_sidebar_groups(games, [], lib.title)
    assert sorted(g.name for row in groups for g in row.games) == ['Korean patch DLC', 'Regular Game']


def test_sidebar_ui_retains_manual_add_and_sort_without_category_ui():
    text = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8') + _ui_main
    assert "add_manual.setObjectName('LibraryAdd')" in text
    assert "self.sort_button.setMinimumWidth(95)" in text
    assert 'set_game_category' not in text
    assert '패치·DLC' not in text
    assert '게임만 표시' not in text
    assert '자료 유형' not in text
