"""Dark, accessible selection menu for Qt widgets.

QComboBox's popup can inherit a native white viewport while the text remains
light under Windows Fusion / frameless dialog styles. This widget deliberately
uses a QMenu with explicit foreground/background colors instead.
"""
from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QMenu


DARK_POPUP_STYLE = """
QMenu {
    background-color:#182a3b;
    color:#ecf4fc;
    border:1px solid #4b6b85;
    padding:5px;
    font-family:'Malgun Gothic','Segoe UI',sans-serif;
    font-size:13px;
}
QMenu::item {
    color:#ecf4fc;
    background-color:#182a3b;
    padding:9px 18px 9px 25px;
    margin:2px 1px;
    min-height:20px;
}
QMenu::item:selected { background-color:#365a76; color:#ffffff; }
QMenu::item:disabled { color:#8092a2; }
QMenu::indicator:checked { image:none; }
"""


def draw_menu_chevron(painter, cx, cy, *, expanded, half_width, tip_height):
    """Draw a menu arrow while preserving each widget's own geometry and pen."""
    path = QPainterPath()
    if expanded:
        path.moveTo(cx - half_width, cy + 2)
        path.lineTo(cx, cy - tip_height)
        path.lineTo(cx + half_width, cy + 2)
    else:
        path.moveTo(cx - half_width, cy - 2)
        path.lineTo(cx, cy + tip_height)
        path.lineTo(cx + half_width, cy - 2)
    painter.drawPath(path)


def add_selection_actions(menu, entries, current_index, select):
    """Populate checkable menu options with their original index callbacks."""
    for index, (label, _data) in enumerate(entries):
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(index == current_index)
        action.triggered.connect(lambda _checked=False, i=index: select(i))


class DarkMenuSelect(QPushButton):
    """Dropdown selector whose options always have a dark, readable popup.

    The small public API mirrors the subset of QComboBox used by this project:
    addItem(s), currentIndex, setCurrentIndex, findData, currentData,
    currentText and currentIndexChanged. No native combo popup is shown.
    """
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[tuple[str, object]] = []
        self._index = -1
        self._menu: QMenu | None = None
        self._menu_open = False
        self._last_closed = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(37)
        self.setObjectName('DarkMenuSelect')
        self.setStyleSheet('''
            QPushButton#DarkMenuSelect {
                background-color:#1e3143; color:#f3f8fc;
                border:1px solid #496b82; border-radius:4px;
                padding:8px 31px 8px 11px;
                text-align:left;
            }
            QPushButton#DarkMenuSelect:hover { background-color:#28465e; border-color:#76a6c2; }
            QPushButton#DarkMenuSelect:pressed { background-color:#31546e; }
        ''')
        self.clicked.connect(self._show_menu)

    def addItem(self, text: str, userData=None):
        self._entries.append((str(text), userData))
        if self._index < 0:
            self.setCurrentIndex(0)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def findData(self, value):
        for index, (_label, data) in enumerate(self._entries):
            if data == value:
                return index
        return -1

    def currentIndex(self):
        return self._index

    def currentText(self):
        return self._entries[self._index][0] if 0 <= self._index < len(self._entries) else ''

    def currentData(self):
        return self._entries[self._index][1] if 0 <= self._index < len(self._entries) else None

    def setCurrentIndex(self, index: int):
        if index < 0 or index >= len(self._entries) or index == self._index:
            return
        self._index = index
        self.setText(self._entries[index][0])
        self.currentIndexChanged.emit(index)
        self.update()

    def _show_menu(self):
        if self._menu is not None and self._menu.isVisible():
            self._menu.close()
            return
        # On some Windows configurations the same mouse click closes a popup
        # and is delivered to the underlying button. Do not reopen it.
        if monotonic() - self._last_closed < 0.15:
            return
        menu = QMenu(self)
        menu.setStyleSheet(DARK_POPUP_STYLE)
        menu.setMinimumWidth(self.width())
        add_selection_actions(menu, self._entries, self._index, self.setCurrentIndex)
        self._menu = menu
        self._menu_open = True
        self.update()

        def on_hide():
            if self._menu is menu:
                self._menu = None
            self._menu_open = False
            self._last_closed = monotonic()
            self.update()
            menu.deleteLater()

        menu.aboutToHide.connect(on_hide)
        menu.popup(self.mapToGlobal(QPoint(0, self.height() + 2)))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor('#d4e7f5'), 1.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cx, cy = self.width() - 16, self.height() / 2
        draw_menu_chevron(painter, cx, cy, expanded=self._menu_open, half_width=5, tip_height=3)
        painter.end()
