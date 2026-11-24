"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QDialog


# Source checkout: internal modules live under src/playdock; frozen builds use PyInstaller --paths.
import sys as _playdock_sys
from pathlib import Path as _playdock_Path
_playdock_source = _playdock_Path(__file__).resolve().parent / "src" / "playdock"
if _playdock_source.is_dir() and str(_playdock_source) not in _playdock_sys.path:
    _playdock_sys.path.insert(0, str(_playdock_source))

from core import Game, Library, load_json, install, uninstall_target, uninstall_to_recycle_bin, executable_candidates, chosen_executable, archive_requires_password, ArchivePasswordRequired, ArchivePasswordInvalid
from services.launch_approval import needs_launch_confirmation, launch_approval_changes, executable_selection_changes
from storage.collections import CollectionStore
from ui.widgets.game_icons import game_art_icon
from cache_management import image_stats, recycle_images
from data_management import inventory, backup_data, inspect_backup, restore_data
from ui.collection_board import CollectionBoard
from models.library_tree import make_sidebar_groups
from artwork import get_secret, set_secret, save_image, discover_local
from ui.selectors import DarkMenuSelect
from storage.setup_paths import save_folder_settings, proposed_paths
from native_caption import windows_dark_caption
from services.launch_options import parse_game_arguments
from work_db import WorkDatabase
from ui.work_info_dialog import WorkLookupThread, WorkPreviewDialog


from ui.styles import MAIN_STYLESHEET as STYLESHEET
from ui.launcher_layout import build_main_ui


























































# Public compatibility imports: existing integrations may import these from app.py.
from ui.widgets.launcher import (collection_chevron, PopupMenuState, LibraryFilterButton,
                                 ChevronMenuButton, friendly_bytes, game_placeholder_icon, Banner)
from ui.dialogs.caption import apply_windows_dark_titlebar, DarkCaptionEventFilter
from ui.dialogs.common import (DialogCloseButton, ThemedDialog, TextEntryDialog, ChoiceDialog,
                               MessageDialog, ask_text, ask_archive_password, ask_choice,
                               ask_yes_no, show_message)
from ui.dialogs.folder_settings import FirstRunDialog
from ui.dialogs.collection_settings import GameCollectionsDialog
from ui.dialogs.cache_manager import CacheManagerDialog
from ui.dialogs.data_manager import DataManagerDialog
from ui.dialogs.library import LibraryInfoDialog
from workers.game_tasks import InstallThread, UninstallThread

from controllers.library import LibraryControllerMixin
from controllers.game_actions import GameActionControllerMixin
from controllers.metadata import MetadataControllerMixin
from controllers.catalog_collection import CatalogCollectionControllerMixin
from controllers.window_actions import WindowActionControllerMixin
from controllers.data_manager import DataManagementController

class MainWindow(LibraryControllerMixin, GameActionControllerMixin, MetadataControllerMixin, CatalogCollectionControllerMixin, WindowActionControllerMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.library = Library()
        self.collections = CollectionStore(self.library.store)
        self.work_db = WorkDatabase(self.library.store, import_legacy=True)
        self.work_lookup_worker = None
        self.identity_lookup_worker = None
        self.catalog_worker = None
        self.catalog_dialog = None
        self.games: list[Game] = []
        self.data_actions = DataManagementController(self)
        self.selected_id: str | None = None
        self.selected_game_item = None
        self.expanded_groups: set[str] = {'__uncategorized__'}
        self.install_worker: InstallThread | None = None
        self.uninstall_worker: UninstallThread | None = None
        self.removing_game: Game | None = None
        self.sort_mode = "name"
        # Single-game title editor is an in-process Qt window.
        self.title_editor_window = None
        self.setWindowTitle("PlayDock")
        icon_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        ico = icon_root / 'assets' / 'playdock.ico'
        if ico.is_file():
            self.setWindowIcon(QIcon(str(ico)))
        self.resize(1380, 840)
        self.setMinimumSize(950, 620)
        self.build_ui()
        self.reload()

    def closeEvent(self, event):
        if self.catalog_worker is not None and self.catalog_worker.isRunning():
            self.catalog_worker.requestInterruption()
            event.ignore()
            if self.catalog_dialog is not None:
                self.catalog_dialog.raise_()
            self.set_message("DB 수집 중단을 요청했습니다. 진행 중인 공식 사이트 조회가 끝나면 종료할 수 있습니다.")
            return
        super().closeEvent(event)

    def action_button(self, label: str, fn, primary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        if primary:
            btn.setObjectName("Primary")
        btn.clicked.connect(fn)
        return btn

    def build_ui(self):
        return build_main_ui(self, LibraryFilterButton=LibraryFilterButton, ChevronMenuButton=ChevronMenuButton, Banner=Banner)
        # No QMainWindow.statusBar(): no permanent status messages.




















    def set_message(self, text: str):
        self.message_timer.stop()
        if not text:
            self.message.hide()
            return
        self.message.setText(text)
        self.message.show()
        self.message_timer.start(5000)

    def library_info_dialog(self):
        dialog = LibraryInfoDialog(self.library, self.games, self)
        dialog.exec()

    def data_manager_dialog(self):
        DataManagerDialog(self).exec()


    def folder_wizard(self):
        dialog = FirstRunDialog(self.library, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.library = Library()
            self.reload()

    @staticmethod
    def tree_identity(item):
        if item is None:
            return None, None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            return data
        return None, None

    def selected_collection(self) -> str:
        item = self.tree.currentItem()
        if item is None:
            return "__uncategorized__"
        kind, value = self.tree_identity(item)
        if kind == "group":
            return value
        if kind == "game" and item.parent() is not None:
            return self.tree_identity(item.parent())[1]
        return "__uncategorized__"



        # Clicking a collection does not clear or change the displayed game.
































def main():
    # Use the same themed Qt chooser for open, folder, and save dialogs.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    from PySide6.QtCore import QTranslator, QLibraryInfo
    translator = QTranslator(app)
    if translator.load("qtbase_ko", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    caption_filter = DarkCaptionEventFilter(app)
    app.installEventFilter(caption_filter)
    library = Library()
    # Existing v0.1.x installations keep their paths; brand-new users see setup once.
    if not library.config_path.is_file() or not library.settings.get("first_run_complete", False):
        if library.config_path.is_file() and all(k in load_json(library.config_path)
                                                     for k in ("library", "archives")):
            library.settings["first_run_complete"] = True
            library.save_settings()
        else:
            dialog = FirstRunDialog(library)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
