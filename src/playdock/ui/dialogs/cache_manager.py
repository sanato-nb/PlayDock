"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
)

from core import Game, Library
from services.cache_service import CacheService


from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog
from ui.dialogs.common import ThemedDialog, ask_yes_no, show_message
from ui.widgets.launcher import friendly_bytes


class CacheManagerDialog(ThemedDialog):
    """Manage artwork cache only, without deleting game metadata or settings."""

    def __init__(self, library: Library, games: list[Game], parent=None, *, actions=None):
        super().__init__("이미지 캐시 관리", parent, 610)
        self.library = library
        self.actions = actions if actions is not None else CacheService(library.cache)
        self.games = list(games)
        heading = QLabel("이미지 캐시 관리")
        heading.setObjectName("Heading")
        self.body.addWidget(heading)
        note = QLabel(
            "배너 및 게임 아이콘 캐시만 정리합니다.\n"
            "게임 이름, 실행 파일 선택, 모음집, ZIP·7z·RAR 및 설치된 게임은 유지됩니다."
        )
        note.setObjectName("Subtle")
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.summary = QLabel("")
        self.summary.setObjectName("DialogHeading")
        self.body.addWidget(self.summary)
        label = QLabel("게임별 이미지 캐시")
        self.body.addWidget(label)
        self.game_search = QLineEdit()
        self.game_search.setPlaceholderText('게임 이름 검색...')
        self.game_search.setClearButtonEnabled(True)
        self.game_search.textChanged.connect(self.filter_games)
        self.body.addWidget(self.game_search)
        self.game_list = QListWidget()
        self.game_list.setMinimumHeight(190)
        self.game_list.setMaximumHeight(240)
        for game in sorted(self.games, key=lambda g: self.library.title(g).casefold()):
            item = QListWidgetItem(self.library.title(game))
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            self.game_list.addItem(item)
        self.game_list.currentItemChanged.connect(self.refresh)
        self.body.addWidget(self.game_list)
        self.selected_size = QLabel("")
        self.selected_size.setObjectName('Subtle')
        self.body.addWidget(self.selected_size)
        row = QHBoxLayout()
        one = QPushButton("선택 게임 이미지 정리")
        one.clicked.connect(self.clear_selected)
        row.addWidget(one)
        all_button = QPushButton("전체 이미지 캐시 정리")
        all_button.clicked.connect(self.clear_all)
        row.addWidget(all_button)
        self.body.addLayout(row)
        warn = QLabel(
            "이미지는 휴지통으로 이동합니다. 직접 지정하거나 GPT로 만든 이미지도 포함되며, "
            "원본이 없다면 자동 복구되지 않을 수 있습니다. "
            "EXE 아이콘 등 일부 이미지는 다음 조회 시 자동 재생성됩니다."
        )
        warn.setObjectName("Subtle")
        warn.setWordWrap(True)
        self.body.addWidget(warn)
        bottom = QHBoxLayout()
        folder = QPushButton("캐시 폴더 열기")
        folder.clicked.connect(self.open_cache_folder)
        bottom.addWidget(folder)
        bottom.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        self.body.addLayout(bottom)
        self.refresh()

    def filter_games(self, query: str):
        key = query.strip().casefold()
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            item.setHidden(key not in item.text().casefold())

    def selected_game_id(self):
        item = self.game_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item and not item.isHidden() else None

    def refresh(self, *_args):
        overall = self.actions.image_stats()
        self.summary.setText(
            f"이미지 캐시: {overall.files}개 · {friendly_bytes(overall.bytes)}"
        )
        cid = self.selected_game_id()
        selected = self.actions.image_stats([cid]) if cid else None
        self.selected_size.setText(
            f"선택 게임: {selected.files}개 · {friendly_bytes(selected.bytes)}"
            if selected else "정리할 게임을 선택해 주세요."
        )

    def clear_selected(self):
        cid = self.selected_game_id()
        if not cid:
            show_message(self, "게임 선택", "먼저 게임을 선택해 주세요.")
            return
        self.clear_images([cid])

    def clear_all(self):
        self.clear_images(None)

    def clear_images(self, ids):
        stats = self.actions.image_stats(ids)
        if not stats.files:
            show_message(self, "이미지 캐시", "정리할 이미지 파일이 없습니다.")
            return
        if not ask_yes_no(self, "이미지 캐시 정리",
              f"이미지 {stats.files}개 ({friendly_bytes(stats.bytes)})를 휴지통으로 이동할까요?\n\n"
              "직접 지정한 이미지도 포함됩니다. 게임 정보·설정·모음집은 삭제되지 않습니다.",
              "정리", "취소"):
            return
        try:
            result = self.actions.recycle_images(ids)
        except Exception as exc:
            show_message(self, "정리 실패", f"이미지 이동에 실패했습니다.\n{exc}")
            self.refresh()
            return
        self.refresh()
        show_message(self, "캐시 정리 완료", f"이미지 {result.files}개를 휴지통으로 이동했습니다.")

    def open_cache_folder(self):
        path = self.library.cache
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
