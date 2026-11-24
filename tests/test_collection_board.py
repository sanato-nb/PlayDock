from refactor_test_support import launcher_source, editor_source
"""Collection overview data and code contracts: no Qt required."""
from pathlib import Path
_ui_main = launcher_source()


import ast
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collection_board_model import list_collection_cards, member_games


def fake_games(*ids):
    return [SimpleNamespace(id=ident) for ident in ids]


def test_card_count_excludes_unavailable_games_but_does_not_modify_stored_ids():
    src = [{'id':'col1', 'name':'RPG', 'game_ids':['a','gone','b']}]
    rows = list_collection_cards(src, fake_games('a','b','c'))
    assert rows == [{'id':'col1', 'name':'RPG', 'game_ids':['a','b']}]
    assert src[0]['game_ids'] == ['a','gone','b']


def test_empty_collections_still_have_cards():
    rows = list_collection_cards([{'id':'empty', 'name':'빈 모음집', 'game_ids':[]}], fake_games('game'))
    assert rows == [{'id':'empty','name':'빈 모음집','game_ids':[]}]


def test_game_membership_order_tracks_library_games():
    games = fake_games('b', 'a', 'c')
    assert [g.id for g in member_games(games, ['a','c'])] == ['a','c']


def test_board_has_overview_and_click_navigation_without_network_calls():
    board = (ROOT/'src/playdock/ui/collection_board.py').read_text(encoding='utf8')
    app = (ROOT/'app.py').read_text(encoding='utf8') + _ui_main
    assert 'class CollectionBoard(QScrollArea)' in board
    assert 'self.createRequested.emit' in board
    assert 'self.collectionOpened.emit(cid)' in board
    assert 'self.gameOpened.emit(gid)' in board
    assert "self.collections_nav_btn = collections_nav" in app
    assert "self.main_stack.currentChanged.connect(self.sync_top_navigation)" in app
    assert "button.setChecked(active)" in app
    assert 'self.action_button("내 모음집", self.show_collections_overview)' in app
    assert 'self.main_stack.addWidget(self.collections_board)' in app
    assert 'self.main_stack.setCurrentWidget(self.collections_board)' in app


def test_card_context_menu_and_sidebar_right_click_allow_management():
    board = (ROOT/'src/playdock/ui/collection_board.py').read_text(encoding='utf8')
    app = (ROOT/'app.py').read_text(encoding='utf8') + _ui_main
    assert "self.renameRequested.emit(cid)" in board
    assert "self.deleteRequested.emit(cid)" in board
    assert 'self.collections_board.renameRequested.connect(self.rename_collection)' in app
    assert 'self.collections_board.deleteRequested.connect(self.delete_collection)' in app
    assert 'self.tree.customContextMenuRequested.connect(self.sidebar_context_menu)' in app
    assert 'manage_btn =' not in app


def test_footer_is_empty_and_fixed_height():
    app = (ROOT/'app.py').read_text(encoding='utf8') + _ui_main
    assert 'footer.setObjectName("FooterBar")' in app
    assert 'footer.setFixedHeight(42)' in app
    assert 'outer.addWidget(footer)' in app
    assert 'footer_layout' not in app
    footer_section = app.split('footer = QFrame()',1)[1].split('def show_image_menu',1)[0]
    assert 'addWidget(' not in footer_section.split('outer.addWidget(footer)',1)[0]
