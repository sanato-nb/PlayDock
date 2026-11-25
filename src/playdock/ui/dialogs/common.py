"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import weakref
from pathlib import Path

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


def _add_confirmation_buttons(dialog):
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    ok = QPushButton('OK')
    cancel = QPushButton('Cancel')
    ok.clicked.connect(dialog.accept)
    cancel.clicked.connect(dialog.reject)
    buttons.addWidget(ok)
    buttons.addWidget(cancel)
    dialog.body.addLayout(buttons)


class TextEntryDialog(ThemedDialog):
    def __init__(self, title: str, label: str, parent=None, text: str = ''):
        super().__init__(title, parent, 430)
        prompt = QLabel(label)
        prompt.setObjectName('DialogHeading')
        prompt.setWordWrap(True)
        self.body.addWidget(prompt)
        self.edit = QLineEdit(text)
        self.body.addWidget(self.edit)
        _add_confirmation_buttons(self)
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
        _add_confirmation_buttons(self)
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
