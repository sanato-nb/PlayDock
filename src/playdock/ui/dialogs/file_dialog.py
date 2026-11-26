"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QEvent,
    QSize,
    QStandardPaths,
    QUrl,
)
from PySide6.QtGui import QColor, QPainter, QPen, QIcon, QPixmap, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QLabel,
    QDialog,
    QFileDialog,
    QToolButton,
    QTreeView,
    QListView,
    QDialogButtonBox,
    QSizeGrip,
)

from ui.styles import FILE_DIALOG_STYLESHEET


from ui.dialogs.common import DialogCloseButton


def _file_toolbar_icon(name):
    """Use high-contrast vector strokes instead of Fusion's dark arrow assets."""
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, "#e3edf7"), (QIcon.Mode.Disabled, "#748495")):
        pix = QPixmap(20, 20)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if name in ("backButton", "forwardButton", "toParentButton"):
            if name == "backButton":
                segments = ((4, 10, 16, 10), (4, 10, 10, 4), (4, 10, 10, 16))
            elif name == "forwardButton":
                segments = ((4, 10, 16, 10), (16, 10, 10, 4), (16, 10, 10, 16))
            else:
                segments = ((10, 16, 10, 4), (10, 4, 4, 10), (10, 4, 16, 10))
            for x1, y1, x2, y2 in segments:
                p.drawLine(x1, y1, x2, y2)
        elif name == "newFolderButton":
            p.drawRect(2, 6, 14, 11)
            p.drawLine(2, 6, 2, 3)
            p.drawLine(2, 3, 8, 3)
            p.drawLine(8, 3, 10, 6)
            p.drawLine(12, 10, 18, 10)
            p.drawLine(15, 7, 15, 13)
        elif name == "listModeButton":
            for y in (4, 10, 16):
                p.drawPoint(3, y)
                p.drawLine(7, y, 17, y)
        else:
            p.drawRect(2, 3, 16, 14)
            for y in (8, 12):
                p.drawLine(3, y, 17, y)
            p.drawLine(10, 3, 10, 17)
        p.end()
        icon.addPixmap(pix, mode)
    return icon


def standard_sidebar_urls(existing=()):
    """Use actual per-user OS known locations; never guess a redirected path."""
    result = []
    seen = set()
    def add(url):
        path = url.toLocalFile()
        key = os.path.normcase(os.path.normpath(path)) if path else url.toString()
        if key not in seen and (not path or Path(path).is_dir()):
            seen.add(key)
            result.append(url)
    # Preserve Qt's built-in computer entry and other existing shortcuts.
    for location in (
        QStandardPaths.StandardLocation.DesktopLocation,
        QStandardPaths.StandardLocation.DownloadLocation,
        QStandardPaths.StandardLocation.DocumentsLocation,
        QStandardPaths.StandardLocation.PicturesLocation,
        QStandardPaths.StandardLocation.MusicLocation,
        QStandardPaths.StandardLocation.MoviesLocation,
    ):
        path = QStandardPaths.writableLocation(location)
        if path and Path(path).is_dir():
            add(QUrl.fromLocalFile(path))
    for url in existing:
        add(url)
    home = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation)
    if home and Path(home).is_dir():
        add(QUrl.fromLocalFile(home))
    return result


def style_file_dialog(dialog):
    """Polish the existing Qt chooser; never change filters or file selection."""
    if dialog.property("playdockFileDialogStyled"):
        return
    dialog.setProperty("playdockFileDialogStyled", True)
    dialog.setStyleSheet(FILE_DIALOG_STYLESHEET)
    dialog.setSidebarUrls(standard_sidebar_urls(dialog.sidebarUrls()))
    dialog.setSizeGripEnabled(False)
    for grip in dialog.findChildren(QSizeGrip):
        grip.hide()
    screen = dialog.screen()
    area = screen.availableGeometry() if screen is not None else None
    width = min(900, max(320, area.width() - 48)) if area is not None else 900
    height = min(600, max(240, area.height() - 64)) if area is not None else 600
    dialog.resize(max(dialog.width(), width), max(dialog.height(), height))
    palette = dialog.palette()
    for role, color in ((QPalette.ColorRole.Window, "#1d2835"),
                        (QPalette.ColorRole.Base, "#141e29"),
                        (QPalette.ColorRole.AlternateBase, "#1b2938"),
                        (QPalette.ColorRole.Text, "#edf5fc"),
                        (QPalette.ColorRole.WindowText, "#e5eef7"),
                        (QPalette.ColorRole.Highlight, "#315d7f"),
                        (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    dialog.setPalette(palette)
    labels = QFileDialog.DialogLabel
    for role, label in ((labels.LookIn, "현재 폴더:"),
                        (labels.FileName, "파일 이름:"),
                        (labels.FileType, "파일 형식:"),
                        (labels.Reject, "취소")):
        dialog.setLabelText(role, label)
    accept = ("선택" if dialog.fileMode() == QFileDialog.FileMode.Directory
              else "저장" if dialog.acceptMode() == QFileDialog.AcceptMode.AcceptSave else "열기")
    dialog.setLabelText(labels.Accept, accept)
    for box in dialog.findChildren(QDialogButtonBox):
        for button in box.buttons():
            if box.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
                button.setText(accept)
            elif box.buttonRole(button) == QDialogButtonBox.ButtonRole.RejectRole:
                button.setText("취소")
    for name, tip in (("backButton", "뒤로"), ("forwardButton", "앞으로"),
                      ("toParentButton", "상위 폴더"), ("newFolderButton", "새 폴더"),
                      ("listModeButton", "목록 보기"), ("detailModeButton", "자세히 보기")):
        tool = dialog.findChild(QToolButton, name)
        if tool is not None:
            tool.setIcon(_file_toolbar_icon(name))
            tool.setIconSize(QSize(20, 20))
            tool.setToolTip("")
            tool.setAccessibleName(tip)
    for view in dialog.findChildren(QTreeView):
        view.setAlternatingRowColors(True)
    for view in dialog.findChildren(QListView):
        view.setAlternatingRowColors(True)


class PlayDockFileDialog(QFileDialog):
    """Qt's existing chooser with a PlayDock-owned dark caption.

    Windows' system title bar is not used for this dialog only, so its color
    no longer depends on the system light/dark theme or DWM timing. The
    existing QFileDialog model, filters, acceptance, and navigation remain.
    """

    def __init__(self, parent=None, caption="", directory="", filter="",
                 *, file_mode=QFileDialog.FileMode.ExistingFile,
                 accept_mode=QFileDialog.AcceptMode.AcceptOpen,
                 options=QFileDialog.Option(0), selected_filter=""):
        super().__init__(parent)
        self.setOptions(options | QFileDialog.Option.DontUseNativeDialog)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle(caption)
        self.setModal(True)
        self.setFileMode(file_mode)
        self.setAcceptMode(accept_mode)
        if filter:
            self.setNameFilter(filter)
        if selected_filter:
            self.selectNameFilter(selected_filter)
        if directory:
            initial = Path(directory)
            if file_mode != QFileDialog.FileMode.Directory and not initial.is_dir():
                if str(initial.parent) != ".":
                    self.setDirectory(str(initial.parent))
                self.selectFile(initial.name)
            else:
                self.setDirectory(str(initial))
        style_file_dialog(self)
        self._drag_pos = None
        self._resize_start = None
        self._caption = QFrame(self)
        self._caption.setObjectName("FileDialogCaption")
        self._caption.setStyleSheet(
            "QFrame#FileDialogCaption { background:#111923; border:none;"
            " border-bottom:1px solid #31465a; }"
            "QLabel#FileDialogTitle { color:#e7f1fb; background:transparent;"
            " font-size:13px; font-weight:600; }"
            "QPushButton#DialogClose { background:transparent; border:none;"
            " padding:0; min-width:30px; min-height:26px; }"
            "QPushButton#DialogClose:hover { background:#35506d; }"
        )
        header = QHBoxLayout(self._caption)
        header.setContentsMargins(10, 0, 3, 0)
        header.setSpacing(6)
        self._caption_title = QLabel(caption, self._caption)
        self._caption_title.setObjectName("FileDialogTitle")
        header.addWidget(self._caption_title)
        header.addStretch(1)
        self._caption_close = DialogCloseButton(self._caption)
        self._caption_close.setAutoDefault(False)
        self._caption_close.setDefault(False)
        self._caption_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._caption_close.clicked.connect(self.reject)
        header.addWidget(self._caption_close)
        self.windowTitleChanged.connect(self._caption_title.setText)
        self._caption.installEventFilter(self)
        self._caption_title.installEventFilter(self)
        # Reserve space above the original QFileDialog layout, without
        # moving/replacing any internal file widgets or grid positions.
        layout = self.layout()
        margins = layout.contentsMargins()
        layout.setContentsMargins(max(8, margins.left()), margins.top() + 34,
                                  max(8, margins.right()), max(8, margins.bottom()))
        self.setMouseTracking(True)
        self._position_caption()

    def _position_caption(self):
        if hasattr(self, "_caption"):
            self._caption.setGeometry(4, 4, max(1, self.width() - 8), 30)
            self._caption.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_caption()

    def eventFilter(self, watched, event):
        if watched in (getattr(self, "_caption", None),
                       getattr(self, "_caption_title", None)):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                handle = self.windowHandle()
                if handle is None or not handle.startSystemMove():
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_pos is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_pos = None
                return True
        return super().eventFilter(watched, event)

    def _resize_edges(self, point):
        edges = Qt.Edge(0)
        if point.x() < 6:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.width() - 6:
            edges |= Qt.Edge.RightEdge
        if point.y() < 4:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self.height() - 6:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._resize_edges(event.position().toPoint())
            if edges:
                handle = self.windowHandle()
                if handle is not None and handle.startSystemResize(edges):
                    return
                self._resize_start = (edges, event.globalPosition().toPoint(), self.geometry())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            edges, start, rect = self._resize_start
            delta = event.globalPosition().toPoint() - start
            from PySide6.QtCore import QRect
            target = QRect(rect)
            min_width = max(self.minimumWidth(), self.minimumSizeHint().width())
            min_height = max(self.minimumHeight(), self.minimumSizeHint().height())
            if edges & Qt.Edge.LeftEdge:
                target.setLeft(min(rect.left() + delta.x(), rect.right() - min_width + 1))
            if edges & Qt.Edge.RightEdge:
                target.setRight(max(rect.right() + delta.x(), rect.left() + min_width - 1))
            if edges & Qt.Edge.TopEdge:
                target.setTop(min(rect.top() + delta.y(), rect.bottom() - min_height + 1))
            if edges & Qt.Edge.BottomEdge:
                target.setBottom(max(rect.bottom() + delta.y(), rect.top() + min_height - 1))
            self.setGeometry(target)
            return
        edges = self._resize_edges(event.position().toPoint())
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            same = bool(edges & Qt.Edge.LeftEdge) == bool(edges & Qt.Edge.TopEdge)
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if same else Qt.CursorShape.SizeBDiagCursor)
        elif horizontal:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif vertical:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_start = None
        super().mouseReleaseEvent(event)

    @classmethod
    def _choose(cls, parent, caption, directory, filter, selectedFilter,
                options, file_mode, accept_mode):
        dialog = cls(parent, caption, directory, filter, file_mode=file_mode,
                     accept_mode=accept_mode, options=options,
                     selected_filter=selectedFilter)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                if selected:
                    return selected[0], dialog.selectedNameFilter()
            return "", ""
        finally:
            dialog.deleteLater()

    @classmethod
    def getOpenFileName(cls, parent=None, caption="", dir="", filter="",
                        selectedFilter="", options=QFileDialog.Option(0)):
        return cls._choose(parent, caption, dir, filter, selectedFilter, options,
                           QFileDialog.FileMode.ExistingFile, QFileDialog.AcceptMode.AcceptOpen)

    @classmethod
    def getSaveFileName(cls, parent=None, caption="", dir="", filter="",
                        selectedFilter="", options=QFileDialog.Option(0)):
        return cls._choose(parent, caption, dir, filter, selectedFilter, options,
                           QFileDialog.FileMode.AnyFile, QFileDialog.AcceptMode.AcceptSave)

    @classmethod
    def getExistingDirectory(cls, parent=None, caption="", dir="",
                             options=QFileDialog.Option.ShowDirsOnly):
        folder, _ = cls._choose(parent, caption, dir, "", "",
                               options | QFileDialog.Option.ShowDirsOnly,
                               QFileDialog.FileMode.Directory, QFileDialog.AcceptMode.AcceptOpen)
        return folder
