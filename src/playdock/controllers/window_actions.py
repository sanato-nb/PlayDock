"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations


from PySide6.QtWidgets import QMenu

from ui.dialogs.database_status import DatabaseStatusDialog


class WindowActionControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def show_settings_menu(self):
        menu = QMenu(self.settings_menu_btn)
        menu.addAction("폴더 설정...").triggered.connect(
            lambda _checked=False: self.folder_wizard())
        menu.addAction("데이터 관리...").triggered.connect(
            lambda _checked=False: self.data_manager_dialog())
        menu.addAction("라이브러리 속성...").triggered.connect(
            lambda _checked=False: self.library_info_dialog())
        menu.addAction("AI 설정...").triggered.connect(
            lambda _checked=False: self.settings_dialog())
        menu.addSeparator()
        menu.addAction("DB 상태 확인...").triggered.connect(
            lambda _checked=False: self.show_database_status())
        menu.addSeparator()
        menu.addAction('게임 이름 설정 (여러 게임)...', self.open_bulk_name_settings)
        menu.addAction('내 이미지 보관 폴더 열기', self.open_artwork_library)
        self.settings_menu_btn.present_popup(menu, right_align=True)


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

        rename = menu.addAction('게임 이름 변경 (수동)…', self.rename_selected_game)
        rename.setEnabled(game is not None)

        images = menu.addMenu('배너·아이콘 수동 설정')
        images.setEnabled(game is not None)
        images.addAction('배너 이미지 선택…', lambda: self.change_image("hero"))
        images.addAction('아이콘 이미지 선택…', lambda: self.change_image("icon"))

        launch = menu.addAction('실행 옵션 설정…', self.edit_launch_options)
        launch.setEnabled(game is not None and game.installed)

        official = menu.addAction('공식 작품 페이지 열기', self.open_saved_official_page)
        official.setEnabled(game is not None)
        self.extra_menu_btn.present_popup(menu, right_align=True)
