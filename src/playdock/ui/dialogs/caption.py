"""Native dark caption filters for main-window and title-editor dialogs."""
from __future__ import annotations

import weakref
from PySide6.QtCore import QTimer, QObject, QEvent
from PySide6.QtWidgets import QWidget, QMainWindow, QDialog, QFileDialog, QToolTip
from native_caption import windows_dark_caption
from ui.dialogs.file_dialog import PlayDockFileDialog, style_file_dialog


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
        if event.type() == QEvent.Type.ToolTip:
            QToolTip.hideText()
            return True
        # The chooser owns its dark caption; DWM must not restyle it.
        if isinstance(watched, PlayDockFileDialog):
            return False
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


class DarkDialogCaptionFilter(QObject):
    """Apply the app's native dark caption to title-editor popups as well."""
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ToolTip:
            QToolTip.hideText()
            return True
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange)
                and isinstance(watched, QDialog) and watched.isWindow()):
            ref = weakref.ref(watched)
            QTimer.singleShot(0, lambda: self.update_caption(ref))
        return False

    @staticmethod
    def update_caption(ref):
        dlg = ref()
        if dlg is not None:
            try:
                windows_dark_caption(int(dlg.winId()))
            except (RuntimeError, TypeError, ValueError, OverflowError):
                pass
