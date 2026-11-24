"""Opt-in DLsite catalogue lookup UI. Never silently edits a game title."""
from __future__ import annotations

import webbrowser
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QCheckBox, QPushButton)
from ui.selectors import DarkMenuSelect
from workers.work_lookup import WorkLookupThread  # 기존 import 호환


class WorkPreviewDialog(QDialog):
    """Show provenance; checkbox is opt-in even for a code-only filename."""

    def __init__(self, record: dict, *, is_cached=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('작품 정보 확인 · PlayDock DB')
        self.resize(620, 430)
        self.record = record
        layout = QVBoxLayout(self)
        lead = QLabel('저장된 작품 정보' if is_cached else 'DLsite 조회 결과 (사용자 확인 필요)')
        lead.setStyleSheet('font-size:17px; font-weight:700;')
        layout.addWidget(lead)
        hint = QLabel('DLsite 웹사이트 JSON을 통한 비공식 조회입니다. 작품 정보와 이미지의 정확성·재사용 권한을 확인하세요.\n'
                      '저장할 때도 실제 압축파일, 게임 설치 파일, 기존 이미지는 변경하지 않습니다.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for label, value in (
            ('작품 코드', record['code']),
            ('제작사', record.get('maker') or '정보 없음'),
            ('장르·태그', ', '.join(record.get('tags', [])[:12]) or '정보 없음'),
            ('이미지', f"표지/샘플 URL {len(record.get('images', []))}개 (이미지는 자동 저장하지 않음)"),
        ):
            line = QLabel(f'{label}:  {value}')
            line.setWordWrap(True)
            layout.addWidget(line)
        self.languages = DarkMenuSelect()
        for lang, label in (('ko', '한국어'), ('ja', '日本語'), ('en', 'English')):
            name = record.get('titles', {}).get(lang)
            if name:
                self.languages.addItem(f'{label} · {name[:55]}', lang)
        if self.languages.currentIndex() < 0:
            self.languages.addItem('작품명 (언어 미확인)', 'fallback')
        layout.addWidget(QLabel('표시 제목에 사용할 정보 (저장 옵션)'))
        layout.addWidget(self.languages)
        self.apply_title = QCheckBox('선택한 작품명을 현재 게임의 표시 이름에도 적용')
        self.apply_title.setChecked(False)
        layout.addWidget(self.apply_title)
        self.open_page = QPushButton('DLsite 원본 페이지 열기')
        self.open_page.clicked.connect(lambda: webbrowser.open(record.get('page_url', '')))
        layout.addWidget(self.open_page)
        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.accept_button = QPushButton('DB에 저장' if not is_cached else '확인')
        self.accept_button.setObjectName('Blue')
        self.accept_button.clicked.connect(self.accept)
        buttons.addWidget(self.accept_button)
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def selected_title(self) -> str:
        language = self.languages.currentData()
        return self.record.get('titles', {}).get(language) or self.record.get('fallback_title', '')
