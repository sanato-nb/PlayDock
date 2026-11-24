"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QDialogButtonBox,
    QTabWidget,
)

from core import Game, Library
from storage.collections import CollectionStore
from services.collection_service import CollectionMembershipActions
from services.cache_service import CacheService
from services.settings_service import save_folder_settings, proposed_paths


from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog
from ui.dialogs.common import ThemedDialog, ask_text, ask_yes_no, show_message
from ui.widgets.launcher import friendly_bytes


class FirstRunDialog(ThemedDialog):
    def __init__(self, library: Library, parent=None):
        self.library = library
        super().__init__("PlayDock · 폴더 설정 마법사", parent, 690)
        layout = self.body
        heading = QLabel("게임 라이브러리를 시작하기")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        msg = QLabel("게임 압축파일 보관 위치와 게임 설치 위치를 지정하세요.\n"
                     "기존 게임 파일을 삭제하거나 이동하지 않습니다.")
        msg.setObjectName("Subtle")
        layout.addWidget(msg)
        default_archive, default_game = proposed_paths()
        current_archive = library.archive_root if library.config_path.exists() else default_archive
        current_game = library.root if library.config_path.exists() else default_game
        self.fields = []
        for title, default in (("① ZIP / 7z / RAR 압축파일 폴더", current_archive),
                               ("② 게임 설치 폴더", current_game)):
            label = QLabel(title)
            layout.addWidget(label)
            line = QHBoxLayout()
            entry = QLineEdit(str(default))
            choose = QPushButton("찾아보기")
            choose.clicked.connect(lambda _checked=False, edit=entry: self.choose_directory(edit))
            line.addWidget(entry, 1)
            line.addWidget(choose)
            layout.addLayout(line)
            self.fields.append(entry)
        info = QLabel("선택한 폴더가 없으면 자동으로 생성합니다. 상단 설정 메뉴의 폴더 설정에서 변경할 수 있습니다.")
        info.setWordWrap(True)
        info.setObjectName("Subtle")
        layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("설정 완료")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_directory(self, edit: QLineEdit):
        starting = Path(edit.text()).expanduser()
        while not starting.is_dir() and starting != starting.parent:
            starting = starting.parent
        folder = QFileDialog.getExistingDirectory(
            self, "폴더 선택", str(starting),
            options=QFileDialog.Option.DontUseNativeDialog)
        if folder:
            edit.setText(folder)

    def save(self):
        try:
            save_folder_settings(self.fields[0].text(), self.fields[1].text())
            self.accept()
        except Exception as exc:
            show_message(self, "폴더 설정 실패", str(exc))
