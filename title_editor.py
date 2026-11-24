"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow


# Source checkout: internal modules live under src/playdock; frozen builds use PyInstaller --paths.
import sys as _playdock_sys
from pathlib import Path as _playdock_Path
_playdock_source = _playdock_Path(__file__).resolve().parent / "src" / "playdock"
if _playdock_source.is_dir() and str(_playdock_source) not in _playdock_sys.path:
    _playdock_sys.path.insert(0, str(_playdock_source))

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













from workers.title import TitleWorker, BulkTitleWorker
from ui.dialogs.title import (DarkDialogCaptionFilter, BulkPreviewDialog,
                              KoreanWebCandidatesDialog, BulkTitleSettingsDialog)
from controllers.title_editor import TitleEditorActionsMixin

class TitleEditor(TitleEditorActionsMixin, QMainWindow):
    closed = Signal()

    def __init__(self, initial_game_id: str | None = None,
                 *, library: Library | None = None, single_game_only: bool = False):
        super().__init__()
        self.library = library if library is not None else Library()
        self.single_game_only = bool(single_game_only)
        self.single_game_id = initial_game_id if single_game_only else None
        self.setStyleSheet(STYLE)
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
        self.setWindowTitle('PlayDock · 이 게임 이름 설정' if single_game_only else
                            'PlayDock · 게임 이름 관리자')
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'playdock.ico'
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1080, 690)
        self.setMinimumSize(800, 520)
        self.make_ui()
        if self.single_game_only:
            self.bulk_settings_btn.hide()
            self.bulk_btn.hide()
            self.search.hide()
            self.setMinimumSize(760, 510)
            self.resize(980, 660)
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
