"""Read-only unified database status in PlayDock's settings."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QHBoxLayout

from services.database_status_service import database_status, format_database_status
from ui.dialogs.common import ThemedDialog


class DatabaseStatusDialog(ThemedDialog):
    def __init__(self, store: str | Path, live_games: int, parent=None, *,
                 scanner_path: str | Path | None = None):
        super().__init__("PlayDock · DB 상태", parent, 720)
        self.resize(790, 570)
        self.store = Path(store)
        self.scanner_path = scanner_path  # ignored: unified shared DB
        self.live_games = live_games
        heading = QLabel("데이터베이스 상태")
        heading.setObjectName("Heading")
        self.body.addWidget(heading)
        note = QLabel("PlayDock에 저장된 공식 작품정보와 게임 연결 상태를 확인합니다.\n"
                      "상태 확인은 읽기 전용이며 게임 파일이나 DB를 변경하지 않습니다.")
        note.setWordWrap(True)
        note.setObjectName("Subtle")
        self.body.addWidget(note)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setStyleSheet(
            "QPlainTextEdit { background:#132232; color:#e7f1fa; "
            "border:1px solid #365369; border-radius:4px; "
            "font-family:'Malgun Gothic','Segoe UI',sans-serif; "
            "font-size:12px; padding:8px; }"
        )
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.details.setMinimumHeight(360)
        self.body.addWidget(self.details, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        retry = QPushButton("상태 다시 확인")
        retry.clicked.connect(self.refresh_status)
        buttons.addWidget(retry)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        self.body.addLayout(buttons)
        self.refresh_status()

    def refresh_status(self):
        report = database_status(self.store, scanner_path=self.scanner_path)
        self.details.setPlainText(
            format_database_status(report, live_games=self.live_games)
        )
