"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

import weakref

from PySide6.QtCore import Qt, QUrl, QTimer, QObject, QEvent
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
)

from core import Library
from database.work_repository import WorkDatabase
from services.bulk_title_service import BulkTitleActions, valid_korean_candidate
from native_caption import windows_dark_caption
from services.localized_titles import LANGUAGES, is_code_only_title
from ui.selectors import DarkMenuSelect


from workers.title import BulkTitleWorker


class BulkPreviewDialog(QDialog):
    """Opt-in review; no game data changes until user confirms checked rows."""
    def __init__(self, rows, requested_language: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('품번만 있는 게임 · 이름 조회 결과')
        self.resize(1020, 620)
        self.rows = rows
        self.requested_language = requested_language
        layout = QVBoxLayout(self)
        explanation = QLabel(
            '체크한 작품만 저장합니다. 언어가 다른 후보는 기본적으로 선택하지 않습니다.\n'
            '실제 게임 파일명, 설치 위치, 모음집은 변경하지 않습니다.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.table = QTableWidget(len(rows), 5)
        self.table.setHorizontalHeaderLabels(['적용', '현재 표시', '조회한 작품명', '언어', '조회 상태'])
        self.table.verticalHeader().hide()
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for row_index, record in enumerate(rows):
            has_title = bool(record.get('title'))
            checkbox = QTableWidgetItem('')
            checkbox.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled |
                              Qt.ItemFlag.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.CheckState.Checked if has_title and
                                   record.get('language') == requested_language
                                   else Qt.CheckState.Unchecked)
            self.table.setItem(row_index, 0, checkbox)
            values = [record.get('original', ''), record.get('title', '조회 실패'),
                      LANGUAGES.get(record.get('language'), ('-', ''))[0],
                      record.get('error') or record.get('source', '')]
            for col, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row_index, col, item)
            self.table.setRowHeight(row_index, 47)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        apply = QPushButton('선택한 제목 저장')
        apply.setObjectName('Save')
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def selected_rows(self):
        return [record for i, record in enumerate(self.rows)
                if record.get('title') and
                self.table.item(i, 0).checkState() == Qt.CheckState.Checked]


class KoreanWebCandidatesDialog(QDialog):
    """Review unverified web headings; never silently change localized titles."""
    def __init__(self, suggestions, parent=None):
        super().__init__(parent)
        self.suggestions = list(suggestions)
        self.setWindowTitle('한국어 작품명 웹 검색 결과 · 사용자 확인')
        self.resize(770, 580)
        layout = QVBoxLayout(self)
        introduction = QLabel('인터넷 검색 결과에서 발견된 한국어 제목 후보입니다.\n'
            '공식 제목으로 검증된 것은 아니니 출처를 확인하고 필요하면 직접 수정한 뒤 선택하세요.')
        introduction.setWordWrap(True)
        introduction.setObjectName('Muted')
        layout.addWidget(introduction)
        self.listing = QListWidget()
        for suggestion in self.suggestions:
            url_host = QUrl(suggestion.url).host()
            item = QListWidgetItem(f'{suggestion.title}  ·  {url_host}')
            self.listing.addItem(item)
        self.listing.currentRowChanged.connect(self.select_candidate)
        layout.addWidget(self.listing, 1)
        layout.addWidget(QLabel('선택할 한국어 제목 (수정 가능)'))
        self.choice = QLineEdit()
        self.choice.setPlaceholderText('출처를 확인하고 사용할 한국어 제목을 입력하세요')
        layout.addWidget(self.choice)
        self.details = QLabel('')
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setObjectName('Muted')
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.open_source_btn = QPushButton('출처 페이지 열기')
        self.open_source_btn.clicked.connect(self.open_source)
        buttons.addWidget(self.open_source_btn)
        buttons.addStretch(1)
        apply = QPushButton('이 제목을 후보로 사용')
        apply.setObjectName('Save')
        apply.clicked.connect(self.accept_candidate)
        buttons.addWidget(apply)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        if self.suggestions:
            self.listing.setCurrentRow(0)

    def selected_candidate(self):
        row = self.listing.currentRow()
        return self.suggestions[row] if 0 <= row < len(self.suggestions) else None

    def select_candidate(self, _row):
        candidate = self.selected_candidate()
        if candidate is None:
            self.open_source_btn.setEnabled(False)
            return
        self.choice.setText(candidate.title)
        self.details.setText(f'검색 결과 제목: {candidate.page_title}\n'
                             f'설명: {candidate.excerpt}\n출처: {candidate.url}')
        self.open_source_btn.setEnabled(True)

    def open_source(self):
        candidate = self.selected_candidate()
        if candidate:
            QDesktopServices.openUrl(QUrl(candidate.url))

    def accept_candidate(self):
        title = self.choice.text().strip()
        if not valid_korean_candidate(title):
            QMessageBox.warning(self, '제목 확인', '확인할 한국어 제목을 입력해 주세요.')
            return
        if self.selected_candidate() is None:
            return
        self.accept()

    def title_result(self):
        return self.choice.text().strip()
