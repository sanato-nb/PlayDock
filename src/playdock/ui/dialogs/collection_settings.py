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
from ui.dialogs.common import ThemedDialog, ask_text, ask_yes_no, show_message, add_standard_confirmation_box
from ui.widgets.launcher import friendly_bytes


class GameCollectionsDialog(ThemedDialog):
    """Checkbox-based many-to-many collection organizer for one game."""
    def __init__(self, collections: CollectionStore, game: Game, title: str, parent=None):
        self.memberships = CollectionMembershipActions(collections)
        self.game = game
        super().__init__("게임을 모음집에 추가 / 제거", parent, 440)
        layout = self.body
        heading = QLabel(f"{title} · 모음집")
        heading.setObjectName("Heading")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        info = QLabel("여러 모음집에 동시에 추가할 수 있습니다. 게임 파일은 이동하지 않습니다.")
        info.setObjectName("Subtle")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.check_area = QVBoxLayout()
        self.checkboxes: dict[str, QCheckBox] = {}
        layout.addLayout(self.check_area)
        for cid, name, checked in self.memberships.choices_for_game(game.id):
            self.append_choice(cid, name, checked)
        if not self.checkboxes:
            hint = QLabel("아직 모음집이 없습니다. 아래 버튼으로 첫 모음집을 만들어 보세요.")
            hint.setObjectName("Subtle")
            self.check_area.addWidget(hint)
        add = QPushButton("＋ 새 모음집 만들기")
        add.clicked.connect(self.new_collection)
        layout.addWidget(add)
        add_standard_confirmation_box(
            layout, QDialogButtonBox.StandardButton.Save, "적용", self.apply_changes, self.reject)

    def append_choice(self, cid: str, name: str, checked: bool):
        checkbox = QCheckBox(name)
        checkbox.setChecked(checked)
        self.checkboxes[cid] = checkbox
        self.check_area.addWidget(checkbox)

    def new_collection(self):
        name, ok = ask_text(self, "모음집 만들기", "모음집 이름:")
        if not ok:
            return
        try:
            cid, label = self.memberships.create(name)
        except ValueError as exc:
            show_message(self, "모음집 생성 실패", str(exc))
            return
        self.append_choice(cid, label, True)

    def apply_changes(self):
        chosen = {cid for cid, checkbox in self.checkboxes.items() if checkbox.isChecked()}
        try:
            self.memberships.save_memberships(self.game.id, chosen)
            self.accept()
        except Exception as exc:
            show_message(self, "모음집 저장 실패", str(exc))
