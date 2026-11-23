"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations


from PySide6.QtWidgets import QMenu

from ui.dialogs.database_status import DatabaseStatusDialog


class WindowActionControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def show_settings_menu(self):
        """One top-right settings popup; refresh remains the only other button."""
        menu = QMenu(self.settings_menu_btn)
        menu.addAction("이름 설정 (여러 게임)...").triggered.connect(
            lambda _checked=False: self.open_bulk_name_settings())
        menu.addSeparator()
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
        self.settings_menu_btn.present_popup(menu, right_align=True)


    def show_database_status(self):
        """Show actual record counts, paths and SQLite health without writes."""
        DatabaseStatusDialog(self.library.store, len(self.games), parent=self).exec()


    def show_image_menu(self):
        """Only manual/local artwork options; no paid image generation path."""
        menu = QMenu(self.image_menu_btn)
        menu.addAction("배너 이미지 직접 선택...").triggered.connect(
            lambda _checked=False: self.change_image("hero"))
        menu.addAction("게임 아이콘 직접 선택...").triggered.connect(
            lambda _checked=False: self.change_image("icon"))
        menu.addSeparator()
        menu.addAction('로컬 이미지 자동 찾기 (무료)').triggered.connect(
            lambda _checked=False: self.refresh_local_art())
        menu.addAction('내 이미지 보관 폴더 열기').triggered.connect(
            lambda _checked=False: self.open_artwork_library())
        self.image_menu_btn.present_popup(menu, right_align=True)


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
        menu.addAction('이 게임 이름 설정...').triggered.connect(
            lambda _checked=False: self.open_title_editor())
        menu.addAction('여러 게임 이름 설정...').triggered.connect(
            lambda _checked=False: self.open_bulk_name_settings())
        menu.addAction('DLsite 작품 정보 조회 · DB 저장...').triggered.connect(
            lambda _checked=False: self.lookup_work_database())
        menu.addAction('저장된 공식 작품 페이지 열기').triggered.connect(
            lambda _checked=False: self.open_saved_official_page())
        menu.addSeparator()
        menu.addAction('실행 옵션 설정...').triggered.connect(
            lambda _checked=False: self.edit_launch_options())
        menu.addAction('세이브 폴더 백업...').triggered.connect(
            lambda _checked=False: self.backup_saves())
        menu.addAction('세이브 ZIP 복원 (새 폴더)...').triggered.connect(
            lambda _checked=False: self.restore_saves())
        if self.current() is not None and self.current().external:
            menu.addSeparator()
            menu.addAction('수동 등록 게임 연결 해제').triggered.connect(
                lambda _checked=False: self.unregister_manual_game())
        self.extra_menu_btn.present_popup(menu, right_align=True)

