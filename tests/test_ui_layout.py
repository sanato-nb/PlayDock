from refactor_test_support import launcher_source, editor_source
"""Regression checks for the intended Qt UI structure without requiring Qt.

Actual rendering still requires a Windows/PySide6 GUI test.
"""
from pathlib import Path
_ui_main = launcher_source()



APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8") + _ui_main


def test_no_persistent_bottom_status_bar():
    assert "self.statusBar()" not in APP.replace(
        "# No QMainWindow.statusBar(): the persistent bottom strip is removed.", ""
    )
    assert "self.count_label" not in APP


def test_tree_no_extra_left_gutter_and_has_visible_chevrons():
    assert "self.tree.setRootIsDecorated(False)" in APP
    assert "self.tree.setIndentation(10)" in APP
    assert "self.tree.itemClicked.connect(self.on_tree_clicked)" in APP
    assert "item.setIcon(0, collection_chevron(item.isExpanded()))" in APP
    assert "chevron = '▾'" not in APP
    assert "path.lineTo(20, 25)" in APP


def test_activity_notice_is_in_content_and_hidden_by_default():
    assert 'self.message.setObjectName("ActivityNotice")' in APP
    assert "self.message.hide()" in APP
    assert "content.addWidget(self.message)" in APP


def test_filter_uses_vector_button_not_qt_combo_arrow():
    assert "class LibraryFilterButton(PopupMenuState, QPushButton)" in APP
    assert "self.mode_filter = LibraryFilterButton()" in APP
    assert "class LibraryFilterButton" in APP and "def setCurrentIndex(self, index" in APP
    assert "self.mode_filter = QComboBox()" not in APP


def test_native_windows_titlebar_is_dark_without_frameless_window():
    assert "def apply_windows_dark_titlebar(window)" in APP
    assert "from native_caption import windows_dark_caption" in APP
    assert "class DarkCaptionEventFilter(QObject)" in APP
    assert "app.installEventFilter(caption_filter)" in APP
    assert "FramelessWindowHint" not in (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8').split('class MainWindow(LibraryControllerMixin, GameActionControllerMixin, MetadataControllerMixin, WindowActionControllerMixin, QMainWindow):', 1)[1]
