"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QDialogButtonBox,
)

from core import Game, Library


from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog
from ui.dialogs.common import ThemedDialog


class LibraryInfoDialog(ThemedDialog):
    def __init__(self, library: Library, games: list[Game], parent=None):
        super().__init__("라이브러리 속성", parent, 620)
        layout = self.body
        heading = QLabel("라이브러리 속성")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        hint = QLabel("라이브러리의 저장 위치와 게임 수를 확인합니다.")
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        installed = sum(1 for g in games if g.installed)
        meta_root = library.store
        rows = [
            ("압축파일 폴더", str(library.archive_root)),
            ("게임 설치 폴더", str(library.root)),
            ("캐시 / 설정 폴더", str(meta_root)),
            ("총 게임 수", f"{len(games)}개"),
            ("설치된 게임", f"{installed}개"),
            ("미설치 게임", f"{len(games) - installed}개"),
        ]
        info = QLabel()
        from html import escape
        table = ''.join(
            '<tr><td style="padding:6px 18px 6px 0; color:#8ea7b9; white-space:nowrap; vertical-align:top;">'
            + escape(a) + '</td><td style="padding:6px; color:#dceaf6;">' + escape(b) + '</td></tr>'
            for a, b in rows
        )
        info.setText('<table cellspacing="0" cellpadding="0">' + table + '</table>')
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        panel = QFrame()
        panel.setObjectName("InfoCard")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.addWidget(info)
        layout.addWidget(panel)
        data_btn = QPushButton("데이터 관리 (목록 · 모음집 · 캐시 · 백업)")
        data_btn.setObjectName("Soft")
        data_btn.clicked.connect(lambda: parent.data_manager_dialog() if parent else None)
        layout.addWidget(data_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        layout.addWidget(buttons)
