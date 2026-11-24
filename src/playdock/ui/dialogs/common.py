"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import weakref

from PySide6.QtCore import Qt, QTimer, QPointF, QObject, QEvent, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QIcon, QPixmap, QPalette
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QDialog, QFileDialog, QToolButton, QTreeView, QListView, QDialogButtonBox, QSizeGrip,
)

from ui.selectors import DarkMenuSelect
from native_caption import windows_dark_caption
from ui.styles import FILE_DIALOG_STYLESHEET


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


def style_file_dialog(dialog):
    """Polish the existing Qt chooser; never change filters or file selection."""
    if dialog.property("playdockFileDialogStyled"):
        return
    dialog.setProperty("playdockFileDialogStyled", True)
    dialog.setStyleSheet(FILE_DIALOG_STYLESHEET)
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
            tool.setToolTip(tip)
            tool.setAccessibleName(tip)
    for view in dialog.findChildren(QTreeView):
        view.setAlternatingRowColors(True)
    for view in dialog.findChildren(QListView):
        view.setAlternatingRowColors(True)


def apply_windows_dark_titlebar(window) -> bool:
    """Apply the same native dark caption to the main window and all dialogs."""
    try:
        return windows_dark_caption(int(window.winId()))
    except (RuntimeError, TypeError, ValueError, OverflowError):
        # A short-lived dialog might already have been destroyed.
        return False


class DarkCaptionEventFilter(QObject):
    """Theme every top-level Qt dialog automatically, including static dialogs.

    Register before the first-run folder dialog is shown. QTimer is important:
    during QEvent.Show the Windows HWND may not exist yet, while QDialog.exec()
    runs its own event loop and allows the queued update to execute.
    """

    def eventFilter(self, watched, event):
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange)
                and isinstance(watched, QWidget)
                and watched.isWindow()
                and isinstance(watched, (QMainWindow, QDialog))):
            ref = weakref.ref(watched)
            if isinstance(watched, QFileDialog) and event.type() == QEvent.Type.Show:
                style_file_dialog(watched)
            QTimer.singleShot(0, lambda: self._update_caption(ref))
            # QFileDialog can recreate or restyle its native caption after Show.
            if isinstance(watched, QFileDialog) and event.type() == QEvent.Type.Show:
                QTimer.singleShot(100, lambda: self._update_caption(ref))
                QTimer.singleShot(250, lambda: self._update_caption(ref))
        return False

    @staticmethod
    def _update_caption(ref):
        window = ref()
        if window is not None:
            apply_windows_dark_titlebar(window)


class DialogCloseButton(QPushButton):
    """Scalable anti-aliased close icon; no font-specific X glyph."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('DialogClose')
        self.setFixedSize(30, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('닫기')

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor('#e3edf7'), 1.7, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        cx, cy = self.width() / 2, self.height() / 2
        painter.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
        painter.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))
        painter.end()


class ThemedDialog(QDialog):
    def __init__(self, title: str, parent=None, min_width: int = 420):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(min_width)
        self._drag_pos = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        shell = QFrame()
        shell.setObjectName('DialogShell')
        outer.addWidget(shell)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName('DialogHeader')
        self.header.installEventFilter(self)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(12, 8, 8, 8)
        hl.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('DialogTitle')
        hl.addWidget(self.title_label)
        hl.addStretch(1)
        close_btn = DialogCloseButton()
        close_btn.clicked.connect(self.reject)
        hl.addWidget(close_btn)
        shell_layout.addWidget(self.header)
        self.body_widget = QWidget()
        self.body_widget.setStyleSheet('background:transparent;')
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(10)
        shell_layout.addWidget(self.body_widget)

    def eventFilter(self, watched, event):
        if watched is self.header:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_pos = None
                return True
        return super().eventFilter(watched, event)


class TextEntryDialog(ThemedDialog):
    def __init__(self, title: str, label: str, parent=None, text: str = ''):
        super().__init__(title, parent, 430)
        prompt = QLabel(label)
        prompt.setObjectName('DialogHeading')
        prompt.setWordWrap(True)
        self.body.addWidget(prompt)
        self.edit = QLineEdit(text)
        self.body.addWidget(self.edit)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton('OK')
        cancel = QPushButton('Cancel')
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        self.body.addLayout(buttons)
        self.edit.selectAll()
        self.edit.setFocus()

    def value(self):
        return self.edit.text()


class ChoiceDialog(ThemedDialog):
    def __init__(self, title: str, label: str, values: list[str], current: int = 0, parent=None):
        super().__init__(title, parent, 500)
        prompt = QLabel(label)
        prompt.setObjectName('DialogHeading')
        prompt.setWordWrap(True)
        self.body.addWidget(prompt)
        self.combo = DarkMenuSelect()
        self.combo.addItems(values)
        if values:
            self.combo.setCurrentIndex(max(0, min(current, len(values)-1)))
        self.body.addWidget(self.combo)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton('OK')
        cancel = QPushButton('Cancel')
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        self.body.addLayout(buttons)
        self.combo.setFocus()


class MessageDialog(ThemedDialog):
    def __init__(self, title: str, message: str, parent=None, *, yes_no: bool = False, yes_label='Yes', no_label='No'):
        super().__init__(title, parent, 520)
        self._accepted = False
        msg = QLabel(message)
        msg.setObjectName('DialogHeading')
        msg.setWordWrap(True)
        self.body.addWidget(msg)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        if yes_no:
            yes = QPushButton(yes_label)
            no = QPushButton(no_label)
            yes.clicked.connect(self.accept)
            no.clicked.connect(self.reject)
            buttons.addWidget(yes)
            buttons.addWidget(no)
        else:
            ok = QPushButton('OK')
            ok.clicked.connect(self.accept)
            buttons.addWidget(ok)
        self.body.addLayout(buttons)


def ask_text(parent, title: str, label: str, text: str = ''):
    dialog = TextEntryDialog(title, label, parent, text)
    ok = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.value(), ok


def ask_archive_password(parent, archive_name: str) -> tuple[str | None, bool]:
    """Password never enters settings, metadata, cache or log messages."""
    dialog = TextEntryDialog('압축파일 비밀번호',
                             f'암호화된 압축파일입니다.\n{archive_name}\n\n비밀번호:', parent)
    dialog.edit.setEchoMode(QLineEdit.EchoMode.Password)
    dialog.edit.setPlaceholderText('압축파일 비밀번호 입력')
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    value = dialog.value() if accepted else None
    dialog.edit.clear()
    return value, accepted


def ask_choice(parent, title: str, label: str, values: list[str], current: int = 0):
    dialog = ChoiceDialog(title, label, values, current, parent)
    ok = dialog.exec() == QDialog.DialogCode.Accepted
    value = dialog.combo.currentText() if values else ''
    return value, ok


def ask_yes_no(parent, title: str, message: str, yes='Yes', no='No') -> bool:
    dialog = MessageDialog(title, message, parent, yes_no=True, yes_label=yes, no_label=no)
    return dialog.exec() == QDialog.DialogCode.Accepted


def show_message(parent, title: str, message: str):
    MessageDialog(title, message, parent).exec()

