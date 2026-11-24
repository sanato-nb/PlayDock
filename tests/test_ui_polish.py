from refactor_test_support import launcher_source, editor_source
"""Static regression checks for the 0.3.4 visual cleanup.

Rendering is OS-dependent; actual Windows GUI QA is still required.
"""

from pathlib import Path
_ui_main = launcher_source()

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8') + (ROOT / 'src/playdock/ui/styles.py').read_text(encoding='utf-8') + _ui_main


def test_collection_header_has_no_contrasting_label_rectangle():
    assert 'QLabel#SectionTitle { background:transparent;' in SOURCE
    assert 'collection_label.setObjectName("SectionLink")' in SOURCE
    assert 'QPushButton#SectionLink { background:transparent;' in SOURCE


def test_vertical_scrollbar_has_no_native_end_buttons():
    assert 'QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical' in SOURCE
    assert 'height:0px; width:0px;' in SOURCE
    assert 'QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical' in SOURCE
    assert 'QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical' in SOURCE
    assert 'self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)' in SOURCE


def test_popup_menu_buttons_use_painter_chevron_not_font_triangle():
    assert 'class ChevronMenuButton(PopupMenuState, QPushButton):' in SOURCE
    assert 'image_button = ChevronMenuButton("이미지 직접 지정")' in SOURCE
    assert 'more_button = ChevronMenuButton("더보기")' not in SOURCE
    assert 'image_button.clicked.connect(self.show_image_menu)' in SOURCE
    assert 'def show_game_menu(' not in SOURCE
    assert '이미지 관리  ▾' not in SOURCE
    assert 'QPushButton#MenuChevron' in SOURCE


def test_gamelibrary_state_not_moved_into_ui_artifacts():
    assert 'self.collections = CollectionStore(self.library.store)' in SOURCE
    assert 'self.library = Library()' in SOURCE
    assert 'self.tree.itemClicked.connect(self.on_tree_clicked)' in SOURCE
