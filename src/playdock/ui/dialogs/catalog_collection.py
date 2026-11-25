"""Batch official game collection with pre-scan exclusions and AI handoff.

The research prompt becomes available ONLY after collection has completed.
Copy/save never changes PlayDock DB, game files, titles, or artwork.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog
from ui.widgets.presentation import progress_bar, summary_label


class CatalogCollectionDialog(QDialog):
    cancelRequested = Signal()
    importRequested = Signal()

    def __init__(self, total: int, parent=None, *,
                 excluded_no_code=(), prompt_text=""):
        super().__init__(parent)
        self.total = total
        self.no_code = tuple(str(name) for name in excluded_no_code)
        self.prompt_text = str(prompt_text)
        self.running = True
        self.counts = Counter()
        self.import_mode = False
        self.import_reasons = []
        self.setWindowTitle("게임 정보 수집 · PlayDock DB")
        self.resize(780, 580)
        self.setMinimumSize(570, 390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("게임 정보 수집")
        self.heading = title
        title.setObjectName("Heading")
        layout.addWidget(title)
        hint = QLabel(
            "압축파일명이나 등록 정보의 DLsite 품번·Steam App ID로 공식 작품 정보를 확인합니다.\n"
            "품번 또는 App ID가 없는 게임은 공식 조회에서 제외하며, 수집 완료 후 AI 조사 프롬프트를 제공합니다.\n"
            "DB에 저장된 공식 작품 정보는 재사용합니다. 게임 이름과 배너·아이콘은 변경하지 않습니다."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.preflight = QLabel(
            f"공식 조회 대상 {total}개 · 품번·App ID 없음 · 사전 제외 {len(self.no_code)}개"
        )
        self.preflight.setWordWrap(True)
        layout.addWidget(self.preflight)
        self.progress = progress_bar(max(total, 1), initial=0)
        layout.addWidget(self.progress)
        self.summary = summary_label(f"0 / {total}개 공식 정보 조회 준비 중")
        layout.addWidget(self.summary)

        layout.addWidget(QLabel("공식 조회 제외·실패 내역"))
        self.failures = QPlainTextEdit()
        self.failures.setReadOnly(True)
        self.failures.setPlaceholderText("공식 조회에서 제외되거나 확인에 실패한 게임을 표시합니다.")
        for label in self.no_code:
            self.failures.appendPlainText(f"• {label[:180]} — 품번·App ID 없음 (공식 조회 제외)")
        layout.addWidget(self.failures, 1)

        row = QHBoxLayout()
        self.prompt_copy_button = QPushButton("품번 없는 게임 AI 조사 프롬프트 복사")
        self.prompt_copy_button.setEnabled(False)
        self.prompt_copy_button.clicked.connect(self.copy_missing_prompt)
        row.addWidget(self.prompt_copy_button)
        self.prompt_save_button = QPushButton("TXT 저장")
        self.prompt_save_button.setEnabled(False)
        self.prompt_save_button.clicked.connect(self.save_missing_prompt)
        row.addWidget(self.prompt_save_button)
        self.import_button = QPushButton("AI 결과 가져오기")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.importRequested.emit)
        row.addWidget(self.import_button)
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
        self.summary.setText("중단 요청 중… 이미 저장한 공식 작품 정보는 유지합니다.")

    def on_progress(self, index: int, total: int, event):
        self.counts[event.outcome] += 1
        self.progress.setValue(index)
        self.summary.setText(
            f"{index}/{total}개 · 신규 작품 {self.counts['fetched']}개 · "
            f"기존 DB 재사용 {self.counts['cached']}개 · "
            f"공식 확인 {self.counts['cached'] + self.counts['fetched']}개 · "
            f"공식 조회 실패 {self.counts['excluded']}개 · "
            f"오류 {self.counts['error']}개"
        )
        if event.outcome in ("excluded", "skipped", "error"):
            self.failures.appendPlainText(f"• {event.label[:140]} — {event.message}")

    def on_complete(self, events, interrupted=False):
        self.running = False
        self.counts = Counter(e.outcome for e in events)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        if not interrupted:
            self.progress.setValue(max(self.total, 1))
        handoff_ready = bool(self.no_code and self.prompt_text and not interrupted)
        self.prompt_copy_button.setEnabled(handoff_ready)
        self.prompt_save_button.setEnabled(handoff_ready)
        self.import_button.setEnabled(handoff_ready)
        self.summary.setText(
            f"{'중단됨' if interrupted else '등록 처리 완료' if self.import_mode else '수집 완료'}  |  공식 조회 {len(events)}/{self.total}개\n"
            f"공식 DB 연결 {sum(bool(e.connected) for e in events)}개  ·  신규 작품 {sum(e.saved for e in events)}개  ·  기존 DB 재사용 {self.counts['cached']}개\n"
            f"상세 정보 보강 {sum(e.enriched for e in events)}개  ·  조회 실패 {self.counts['excluded']}개  ·  오류 {self.counts['error']}개\n"
            f"남은 품번 없는 게임 {len(self.no_code)}개"
        )

    def set_remaining(self, missing, prompt, events):
        self.no_code = tuple(e.label for e in missing)
        self.prompt_text = prompt
        self.heading.setText("AI 품번 가져오기 결과")
        self.preflight.setText(f"이번 공식 조회 대상 {self.total}개 · 남은 품번 없는 게임 {len(self.no_code)}개")
        reasons = list(self.import_reasons)
        reasons.extend(f"{e.label} — {e.message}" for e in events if not e.connected)
        self.failures.setPlainText("\n".join(
            [f"• {name} — 품번·App ID 없음" for name in self.no_code] +
            (["\n[조사 및 조회 결과]"] + reasons if reasons else [])))
        self.prompt_copy_button.setText("품번 없는 게임 AI 조사 프롬프트 복사")
        self.prompt_save_button.setText("TXT 저장")

    def on_failed(self, reason):
        self.running = False
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.prompt_copy_button.setEnabled(False)
        self.prompt_save_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.summary.setText(f"수집 중단 · {reason}")
        self.failures.appendPlainText(reason)

    def copy_missing_prompt(self):
        if not self.running and self.prompt_copy_button.isEnabled() and self.prompt_text:
            QApplication.clipboard().setText(self.prompt_text)
            self.prompt_copy_button.setText("복사 완료 · AI 채팅에 붙여넣기")

    def save_missing_prompt(self):
        if self.running or not self.prompt_save_button.isEnabled():
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self, "AI 조사 프롬프트 TXT 저장",
            "PlayDock_품번없는게임_AI조사프롬프트.txt",
            "텍스트 파일 (*.txt)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(self.prompt_text, encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.warning(self, "저장 실패", f"TXT를 저장하지 못했습니다: {exc}")
            return
        self.prompt_save_button.setText("TXT 저장 완료")

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
