"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

import sys
import argparse
import weakref
from urllib.parse import urlencode
from time import sleep
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QThread, Signal, QTimer, QObject, QEvent
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QFrame,
    QMessageBox, QSplitter, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QStackedWidget, QScrollArea, QCheckBox,
)

from core import Library
from simple_title_edit import save_display_title, undo_display_title, restore_filename_title, title_history
from bulk_title_edit import BulkChange, replace_name, name_was_manually_changed, apply_bulk_changes, preview_undo_name
from product_titles import extract_code, display_title, lookup_title
from game_codes import normalize_code
from artwork import ai_game_title, get_secret
from ai_providers import PROVIDERS, current_provider, current_models
from native_caption import windows_dark_caption
from localized_titles import (
    LANGUAGES, is_code_only_title, lookup_localized_title,
    display_language_for, language_is_plausible,
)
from ui.selectors import DarkMenuSelect
from title_translation import translate_work_title
from korean_title_search import find_korean_titles

from ui.styles import EDITOR_STYLESHEET as STYLE
from ui.editor_layout import build_title_editor_ui













from services.title_workers import TitleWorker, BulkTitleWorker
from ui.dialogs.title import (DarkDialogCaptionFilter, BulkPreviewDialog,
                              KoreanWebCandidatesDialog, BulkTitleSettingsDialog)
from controllers.title_editor import TitleEditorActionsMixin

class TitleEditor(TitleEditorActionsMixin, QMainWindow):
    def __init__(self, initial_game_id: str | None = None):
        super().__init__()
        self.library = Library()  # Same settings and metadata as PlayDock.exe
        self.games = []
        self.selected_id: str | None = initial_game_id
        self.worker: TitleWorker | None = None
        self.bulk_worker: BulkTitleWorker | None = None
        self.bulk_results = []
        self.localized_source = '사용자 입력'
        self.localized_candidate_language = 'ko'
        self._loading_localized = False
        self.suggestion_source = '수동 수정'
        self.suggestion_code = ''
        self.setWindowTitle('PlayDock · 게임 이름 관리자')
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'playdock.ico'
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1080, 690)
        self.setMinimumSize(800, 520)
        self.make_ui()
        self.refresh()
        QTimer.singleShot(0, lambda: windows_dark_caption(int(self.winId())))

    def make_ui(self):
        return build_title_editor_ui(self)



































def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--game-id', default=None,
                        help='본체에서 전달한 게임을 이름 관리자에서 선택')
    args, _ = parser.parse_known_args(sys.argv[1:])
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    captions = DarkDialogCaptionFilter(app)
    app.installEventFilter(captions)
    window = TitleEditor(initial_game_id=args.game_id)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
