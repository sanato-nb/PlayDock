"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations


from sqlite3 import Error as SQLiteError
from PySide6.QtWidgets import QMenu

from ui.dialogs.database_status import DatabaseStatusDialog


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
        self.settings_menu_btn.present_popup(menu, right_align=True)


    def function_availability(self):
        """One source of truth for the button and its two menu actions."""
        game = self.current() if self.main_stack.currentWidget() is self.scroll else None
        try:
            artwork = game is not None and self.has_official_image_candidates(game)
            names = any(self.has_collected_game_info(g) for g in self.games)
            return artwork, names
        except (OSError, ValueError, SQLiteError):
            return False, False

    def refresh_function_availability(self):
        artwork, names = self.function_availability()
        self.function_menu_btn.setEnabled(artwork or names)
        self.function_menu_btn.setToolTip(
            "" if artwork or names else "게임 정보 수집 후 사용 가능한 기능입니다."
        )

    def sync_top_navigation(self, *_args):
        library_active = self.main_stack.currentWidget() is self.scroll
        for button, active in ((self.library_nav_btn, library_active),
                               (self.collections_nav_btn, not library_active)):
            button.setChecked(active)
        self.refresh_function_availability()

    def show_function_menu(self):
        """Official-data actions, distinct from one game's four manual tools."""
        menu = QMenu(self.function_menu_btn)
        artwork_enabled, names_enabled = self.function_availability()

        artwork = menu.addAction("공식 배너·아이콘 적용", self.identify_selected_game)
        artwork.setEnabled(artwork_enabled)
        artwork.setToolTip(
            "게임 정보 수집에서 검증된 공식 이미지 URL이 있는 게임만 이용할 수 있습니다."
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

        launch = menu.addAction('실행 옵션 설정', self.edit_launch_options)
        launch.setEnabled(game is not None and game.installed)

        official = menu.addAction('공식 작품 페이지 열기', self.open_saved_official_page)
        official.setEnabled(game is not None and self.has_collected_game_info(game))
        self.extra_menu_btn.present_popup(menu, right_align=True)
