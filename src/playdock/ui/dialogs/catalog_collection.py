"""Modeless batch catalog collection progress: no artwork/title/file edits."""
from __future__ import annotations

from collections import Counter
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPlainTextEdit, QPushButton,
)


class CatalogCollectionDialog(QDialog):
    cancelRequested = Signal()

    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self.total = total
        self.running = True
        self.counts = Counter()
        self.setWindowTitle("게임 정보 수집 · PlayDock DB")
        self.resize(710, 490)
        self.setMinimumSize(570, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("게임 정보 수집")
        title.setObjectName("Heading")
        layout.addWidget(title)
        hint = QLabel(
            "전체 라이브러리의 압축파일명·품번을 확인하고 DLsite → Steam 공식 작품정보를 "
            "PlayDock DB에 저장합니다.\n"
            "이미 저장된 작품은 재사용합니다. 게임 이름과 기존 배너·아이콘은 변경하지 않습니다."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.progress = QProgressBar()
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.summary = QLabel(f"0 / {total}개 확인 · 공식정보 수집 준비 중")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addWidget(QLabel("확인이 필요하거나 수집하지 못한 게임"))
        self.failures = QPlainTextEdit()
        self.failures.setReadOnly(True)
        self.failures.setPlaceholderText("실패 또는 품번 없는 게임이 여기에 표시됩니다.")
        layout.addWidget(self.failures, 1)
        row = QHBoxLayout()
        row.addStretch()
        self.stop_button = QPushButton("중단")
        self.stop_button.clicked.connect(self.request_cancel)
        row.addWidget(self.stop_button)
        self.close_button = QPushButton("닫기")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        row.addWidget(self.close_button)
        layout.addLayout(row)

    def request_cancel(self):
        if not self.running:
            return
        self.cancelRequested.emit()
        self.stop_button.setEnabled(False)
        self.summary.setText("중단 요청 중… 이미 저장한 공식 작품정보는 유지합니다.")

    def on_progress(self, index: int, total: int, event):
        self.counts[event.outcome] += 1
        self.progress.setValue(index)
        self.summary.setText(
            f"{index}/{total}개 · 신규 정보 {self.counts['fetched']}개 · "
            f"DB 재사용 {self.counts['cached']}개 · "
            f"미확인 {self.counts['excluded'] + self.counts['skipped']}개 · "
            f"오류 {self.counts['error']}개"
        )
        if event.outcome in ("excluded", "skipped", "error"):
            self.failures.appendPlainText(f"• {event.label[:110]} — {event.message}")

    def on_complete(self, events, interrupted=False):
        self.running = False
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.summary.setText(
            f"{'중단됨' if interrupted else '수집 완료'} · "
            f"{len(events)}/{self.total}개 확인 · "
            f"신규 {sum(e.saved for e in events)}개 작품 저장 · "
            f"기존 DB {self.counts['cached']}개 재사용 · "
            f"상세정보 보강 {sum(e.enriched for e in events)}개 · "
            f"미확인 {self.counts['excluded'] + self.counts['skipped']}개 · "
            f"오류 {self.counts['error']}개"
        )

    def on_failed(self, reason):
        self.running = False
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.summary.setText(f"수집 중단 · {reason}")
        self.failures.appendPlainText(reason)

    def reject(self):
        if self.running:
            self.request_cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self.running:
            self.request_cancel()
            event.ignore()
            return
        super().closeEvent(event)
