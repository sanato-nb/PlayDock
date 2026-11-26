"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations


import webbrowser
from sqlite3 import Error as SQLiteError
from PySide6.QtWidgets import QMenu

from ui.dialogs.common import show_message
from ui.dialogs.database_status import DatabaseStatusDialog


SUPPORT_URL = "https://fairy.hada.io/@playdock"


class WindowActionControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def show_settings_menu(self):
        menu = QMenu(self.settings_menu_btn)
        menu.addAction("폴더 설정").triggered.connect(
            lambda _checked=False: self.folder_wizard())
        menu.addAction("데이터 관리").triggered.connect(
            lambda _checked=False: self.data_manager_dialog())
        menu.addAction("라이브러리 속성").triggered.connect(
            lambda _checked=False: self.library_info_dialog())
        menu.addSeparator()
        menu.addAction("DB 상태 확인").triggered.connect(
            lambda _checked=False: self.show_database_status())
        menu.addSeparator()
        support_visibility = menu.addAction("개발자 후원 버튼 표시")
        support_visibility.setCheckable(True)
        support_visibility.setChecked(self.library.settings.get("show_support_button", True) is not False)
        support_visibility.toggled.connect(self.set_support_button_visible)
        self.settings_menu_btn.present_popup(menu, right_align=True)

    def set_support_button_visible(self, visible):
        """Persist only this optional UI preference; keep all other settings."""
        settings = self.library.settings
        missing = "show_support_button" not in settings
        previous = settings.get("show_support_button", True)
        settings["show_support_button"] = bool(visible)
        try:
            self.library.save_settings()
        except OSError as exc:
            if missing:
                settings.pop("show_support_button", None)
            else:
                settings["show_support_button"] = previous
            show_message(self, "설정 저장 실패", str(exc))
            return
        self.support_btn.setVisible(bool(visible))

    def open_support_page(self):
        """Open the optional support page only after an explicit user click."""
        try:
            opened = webbrowser.open(SUPPORT_URL)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            show_message(self, "브라우저 실행 실패", SUPPORT_URL)


    def function_availability(self, *, records=None):
        """One source of truth for the button and its two menu actions."""
        try:
            if records is None:
                records = self.collected_library_records()
            artwork = any(self._record_has_official_images(row) for row in records.values())
            return artwork, bool(records)
        except (OSError, ValueError, SQLiteError):
            return False, False

    def refresh_function_availability(self, *, meta_by_game=None):
        records = None
        if meta_by_game is None:
            artwork, names = self.function_availability()
        else:
            try:
                records = self.collected_library_records(meta_by_game=meta_by_game)
                artwork, names = self.function_availability(records=records)
            except (OSError, ValueError, SQLiteError):
                artwork, names = False, False
        self.function_menu_btn.setEnabled(artwork or names)
        self.function_menu_btn.setToolTip(
            "" if artwork or names else "게임 정보 수집 후 사용 가능한 기능입니다."
        )
        return records

    def sync_top_navigation(self, *_args):
        library_active = self.main_stack.currentWidget() is self.scroll
        for button, active in ((self.library_nav_btn, library_active),
                               (self.collections_nav_btn, not library_active)):
            button.setChecked(active)
        self.refresh_function_availability()

    def show_function_menu(self):
        """Whole-library official-data actions, independent of the current selection."""
        menu = QMenu(self.function_menu_btn)
        artwork_enabled, names_enabled = self.function_availability()

        artwork = menu.addAction("공식 배너·아이콘 적용 (여러 게임)", self.open_bulk_official_artwork)
        artwork.setEnabled(artwork_enabled)
        artwork.setToolTip(
            "전체 라이브러리에서 공식 이미지 후보가 있는 게임을 선택하여 적용합니다."
        )

        official_names = menu.addAction(
            "공식 게임명 설정 (여러 게임)", self.open_official_name_settings
        )
        official_names.setEnabled(names_enabled)
        self.function_menu_btn.present_popup(menu, right_align=True)


    def show_database_status(self):
        """Show actual record counts, paths and SQLite health without writes."""
        DatabaseStatusDialog(self.library.store, len(self.games), parent=self).exec()


    def open_sort_menu(self):
        menu = QMenu(self)
        for label, key in [('이름순 (가나다·A-Z)', 'name'), ('이름 역순', 'name_desc'),
                           ('설치됨 먼저', 'installed'), ('압축파일 용량 큰 순', 'archive_size')]:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.sort_mode == key)
            action.triggered.connect(lambda _checked=False, mode=key: self.change_sort(mode))
        self.sort_button.present_popup(menu, right_align=True)


    def change_sort(self, mode):
        self.sort_mode = mode
        self.populate_games()


    def show_extra_menu(self):
        menu = QMenu(self.extra_menu_btn)
        game = self.current() if self.main_stack.currentWidget() is self.scroll else None

        rename = menu.addAction('게임 이름 변경 (수동)', self.rename_selected_game)
        rename.setEnabled(game is not None)

        images = menu.addMenu('배너·아이콘 수동 설정')
        images.setEnabled(game is not None)
        images.addAction('배너 이미지 선택', lambda: self.change_image("hero"))
        images.addAction('아이콘 이미지 선택', lambda: self.change_image("icon"))

        official_images = menu.addAction('공식 배너·아이콘 적용', self.identify_selected_game)
        official_images.setEnabled(game is not None and self.has_official_image_candidates(game))

        launch = menu.addAction('실행 옵션 설정', self.edit_launch_options)
        launch.setEnabled(game is not None and game.installed)

        official = menu.addAction('공식 작품 페이지 열기', self.open_saved_official_page)
        official.setEnabled(game is not None and self.has_collected_game_info(game))
        self.extra_menu_btn.present_popup(menu, right_align=True)
