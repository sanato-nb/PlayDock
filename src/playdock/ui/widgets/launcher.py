"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

from pathlib import Path
from ui.widgets.artwork_cache import artwork_pixmap, cached_pixmap
from ui.selectors import add_selection_actions, draw_menu_chevron
from time import monotonic

from PySide6.QtCore import Qt, Signal, QPoint, QRect, QRectF, QObject, QEvent
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
    QLinearGradient,
    QPen,
    QBrush,
    QPainterPath,
    QCursor,
)
from PySide6.QtWidgets import QWidget, QPushButton, QSizePolicy, QMenu


def _render_collection_chevron(expanded: bool) -> QPixmap:
    """Symmetric anti-aliased arrow; never depends on a Korean font glyph."""
    pic = QPixmap(40, 40)
    pic.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pic)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor('#a6c3d7'), 3.0, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path = QPainterPath()
    if expanded:  # down arrow
        path.moveTo(11, 16)
        path.lineTo(20, 25)
        path.lineTo(29, 16)
    else:  # right arrow
        path.moveTo(16, 11)
        path.lineTo(25, 20)
        path.lineTo(16, 29)
    painter.drawPath(path)
    painter.end()
    pic.setDevicePixelRatio(2)
    return pic


def collection_chevron(expanded: bool) -> QIcon:
    # Let Qt own the cached pixmap's lifetime rather than holding a global
    # Python QIcon cache that may outlive QApplication during shutdown.
    pic = cached_pixmap(('collection-chevron-v1', expanded), ('group-arrow', 40),
                        lambda: _render_collection_chevron(expanded))
    return QIcon(pic)


class CollectionArrowClickFilter(QObject):
    """Handle the custom group arrow before Qt selects the row or emits itemClicked."""
    toggleRequested = Signal(object)

    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree
        self._pressed = None
        tree.viewport().installEventFilter(self)

    def _arrow_at(self, point):
        item = self.tree.itemAt(point)
        if item is None or item.parent() is not None:
            return None
        identity = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(identity, tuple) or len(identity) != 2 or identity[0] != "group":
            return None
        # The existing left-aligned icon is 22px wide with 2px item padding.
        # Give the arrow the whole icon cell, but not the adjacent title.
        rect = self.tree.visualItemRect(item)
        if rect.contains(point) and point.x() < rect.left() + self.tree.iconSize().width() + 4:
            return item, identity
        return None

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.LeftButton:
                hit = self._arrow_at(event.position().toPoint())
                self._pressed = None
                if hit is not None:
                    # A double click should not immediately undo the first toggle.
                    self._pressed = hit[1] if kind == QEvent.Type.MouseButtonPress else ()
                    return True
        elif kind == QEvent.Type.MouseMove and self._pressed is not None:
            return True
        elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            pressed, self._pressed = self._pressed, None
            if pressed is not None:
                hit = self._arrow_at(event.position().toPoint())
                if hit is not None and hit[1] == pressed:
                    self.toggleRequested.emit(hit[0])
                return True
        return super().eventFilter(watched, event)


class PopupMenuState:
    """Reusable popup lifecycle: click toggles, outside click dismisses.

    QMenu.popup() is asynchronous (unlike exec()), so buttons can repaint the
    up-chevron immediately and Qt still handles outside-click dismissal.
    """

    def _init_popup_state(self):
        self._popup_menu: QMenu | None = None
        self._menu_open = False
        self._last_popup_closed = 0.0

    def is_menu_open(self) -> bool:
        return self._menu_open

    def present_popup(self, menu: QMenu, right_align: bool = False):
        if self._popup_menu and self._popup_menu.isVisible():
            self._popup_menu.close()
            menu.deleteLater()
            return
        # Some Windows/Qt versions send the button's click *after* QMenu has
        # handled the same outside press. Don't reopen on that same click.
        if (monotonic() - self._last_popup_closed < 0.14
                and self.rect().contains(self.mapFromGlobal(QCursor.pos()))):
            menu.deleteLater()
            return

        self._popup_menu = menu
        self._menu_open = True
        self.setProperty('menuOpen', True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        def finished():
            if self._popup_menu is menu:
                self._popup_menu = None
                self._menu_open = False
                self._last_popup_closed = monotonic()
                self.setProperty('menuOpen', False)
                self.style().unpolish(self)
                self.style().polish(self)
                self.update()
            menu.deleteLater()

        menu.aboutToHide.connect(finished)
        menu.adjustSize()
        x = self.width() - menu.sizeHint().width() if right_align else 0
        menu.popup(self.mapToGlobal(QPoint(x, self.height() + 2)))


class LibraryFilterButton(PopupMenuState, QPushButton):
    """A compact Steam-style menu button replacing the platform combo arrow."""
    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._options: list[tuple[str, str]] = []
        self._index = 0
        self._init_popup_state()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(180)
        self.clicked.connect(self.open_filter_menu)

    def addItem(self, label: str, data: str):
        self._options.append((label, data))
        self.update()

    def currentIndex(self) -> int:
        return self._index

    def currentData(self):
        return self._options[self._index][1] if self._options else None

    def setCurrentIndex(self, index: int):
        if not 0 <= index < len(self._options) or index == self._index:
            return
        self._index = index
        self.update()
        self.currentIndexChanged.emit(index)

    def open_filter_menu(self):
        menu = QMenu(self)
        add_selection_actions(menu, self._options, self._index, self.setCurrentIndex)
        self.present_popup(menu)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        bg = '#294a63' if self.is_menu_open() else '#294258' if self.isDown() else '#253b50' if self.underMouse() else '#1e3143'
        painter.setPen(QPen(QColor('#53728a' if self.underMouse() else '#355267'), 1))
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(bounds, 6, 6)
        short = {'all': '전체', 'installed': '설치됨', 'uninstalled': '미설치'}
        mode = self.currentData()
        badge_text = short.get(mode, '전체')
        badge_width = max(42, painter.fontMetrics().horizontalAdvance(badge_text) + 17)
        badge_x = self.width() - badge_width - 28
        badge_rect = QRectF(badge_x, 8, badge_width, self.height() - 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#335673'))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor('#a8dafa'))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        painter.setPen(QColor('#e4edf5'))
        # Prefer the stable section label; status lives in its separate badge.
        base_label = '게임 라이브러리'
        text_rect = QRect(12, 0, max(20, int(badge_x) - 20), self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(base_label, Qt.TextElideMode.ElideRight, text_rect.width()))
        # Right-hand chevron is drawn at a fixed 2:1 aspect ratio.
        arrow_x = self.width() - 17
        arrow_y = self.height() // 2
        painter.setPen(QPen(QColor('#afd0e1'), 1.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        draw_menu_chevron(painter, arrow_x, arrow_y, expanded=self.is_menu_open(), half_width=5, tip_height=3)
        painter.end()


class ChevronMenuButton(PopupMenuState, QPushButton):
    """Text button with a fixed-size, anti-aliased vector down-chevron.

    The right side always uses a QPainter path rather than a font glyph,
    avoiding the tiny tilted triangle seen on different Windows fonts/scales.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self._init_popup_state()
        self.setObjectName("MenuChevron")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() - 15
        cy = self.height() / 2
        pen = QPen(QColor('#a9cadc' if self.isEnabled() else '#6e8393'), 1.8,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        draw_menu_chevron(painter, cx, cy, expanded=self.is_menu_open(), half_width=4.5, tip_height=2.5)
        painter.end()


def friendly_bytes(num: int) -> str:
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n:.0f} B"
        n /= 1024
    return f"{n:.1f} TB"


def game_placeholder_icon() -> QIcon:
    """A neutral gamepad, never a folder / ZIP icon or fake cover artwork."""
    pix = QPixmap(56, 56)
    pix.fill(QColor("#1c3347"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#81bbde"), 2.2))
    painter.setBrush(QBrush(QColor("#285875")))
    painter.drawRoundedRect(7, 14, 42, 28, 12, 12)
    painter.setPen(QPen(QColor("#e9f5ff"), 3))
    painter.drawLine(16, 27, 28, 27)
    painter.drawLine(22, 21, 22, 33)
    painter.setPen(QPen(QColor("#bdeafa"), 2.5))
    painter.drawPoint(37, 25)
    painter.drawPoint(42, 31)
    painter.end()
    return QIcon(pix)


class Banner(QWidget):
    def __init__(self):
        super().__init__()
        self.title = "PLAYDOCK"
        self.subtitle = "내 게임 라이브러리"
        self.image = QPixmap()
        self.setMinimumHeight(220)
        self.setMaximumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_game(self, title: str, subtitle: str, image: Path | None):
        self.title, self.subtitle = title, subtitle
        self.image = artwork_pixmap(image)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = self.rect()
        if not self.image.isNull():
            img = self.image
            ratio = max(area.width() / img.width(), area.height() / img.height())
            src_w, src_h = area.width() / ratio, area.height() / ratio
            source = QRectF((img.width() - src_w) / 2, (img.height() - src_h) / 2, src_w, src_h)
            p.drawPixmap(QRectF(area), img, source)
        else:
            gradient = QLinearGradient(0, 0, area.width(), area.height())
            gradient.setColorAt(0, QColor("#1b4159"))
            gradient.setColorAt(0.52, QColor("#265b76"))
            gradient.setColorAt(1, QColor("#152635"))
            p.fillRect(area, gradient)
            p.setPen(QPen(QColor(255, 255, 255, 14), 5))
            for i in range(-8, 15):
                x = i * 130
                p.drawLine(x, 0, x + 490, area.height())
        fade = QLinearGradient(0, 0, area.width() * 0.73, 0)
        fade.setColorAt(0, QColor(6, 13, 20, 210))
        fade.setColorAt(0.65, QColor(8, 17, 25, 85))
        fade.setColorAt(1, QColor(8, 17, 25, 0))
        p.fillRect(area, fade)
        bottom = QLinearGradient(0, area.height() * 0.67, 0, area.height())
        bottom.setColorAt(0, QColor(12, 20, 30, 0))
        bottom.setColorAt(1, QColor(13, 22, 32, 190))
        p.fillRect(area, bottom)
        # Extra contrast only on real artwork; no change to stored image or placeholder.
        if not self.image.isNull():
            text_fade = QLinearGradient(0, area.height()*0.35, 0, area.height())
            text_fade.setColorAt(0, QColor(8, 14, 22, 0))
            text_fade.setColorAt(0.50, QColor(8, 14, 22, 160))
            text_fade.setColorAt(1, QColor(8, 14, 22, 220))
            p.fillRect(area, text_fade)
        font = QFont("Malgun Gothic", 26, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#fcfdff"))
        title_rect = QRect(28, area.height() - 112, max(200, area.width() - 60), 66)
        rendered_title = p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, title_rect.width())
        alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        if not self.image.isNull():
            p.setPen(QColor(0,0,0,210))
            p.drawText(title_rect.translated(1,2), alignment, rendered_title)
            p.setPen(QColor("#fcfdff"))
        p.drawText(title_rect, alignment, rendered_title)
        font = QFont("Malgun Gothic", 11)
        p.setFont(font)
        p.setPen(QColor("#cbdde7"))
        p.drawText(30, area.height() - 26, self.subtitle)
        p.end()

