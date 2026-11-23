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
from services.bulk_title_service import BulkTitleActions, valid_korean_candidate
from services.official_work_service import explicit_work_identity
from native_caption import windows_dark_caption
from localized_titles import LANGUAGES, is_code_only_title
from ui.selectors import DarkMenuSelect


from services.title_workers import BulkTitleWorker


class DarkDialogCaptionFilter(QObject):
    """Apply the app's native dark caption to title-editor popups as well."""
    def eventFilter(self, watched, event):
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange)
                and isinstance(watched, QDialog) and watched.isWindow()):
            ref = weakref.ref(watched)
            QTimer.singleShot(0, lambda: self.update_caption(ref))
        return False

    @staticmethod
    def update_caption(ref):
        dlg = ref()
        if dlg is not None:
            try:
                windows_dark_caption(int(dlg.winId()))
            except (RuntimeError, TypeError, ValueError, OverflowError):
                pass


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


class BulkTitleSettingsDialog(QDialog):
    """Detailed bulk rename: scope -> source -> editable preview -> explicit apply."""

    def __init__(self, library: Library, games, initial_game_id=None, parent=None):
        super().__init__(parent)
        self.library = library
        self.bulk_actions = BulkTitleActions(library)
        self.games = list(games)
        self.worker = None
        self.preview_items = {}
        self.setWindowTitle('일괄 이름 변경 · 상세 설정')
        self.resize(1130, 780)
        self.setMinimumSize(850, 640)
        outer = QVBoxLayout(self)
        heading = QLabel('일괄 게임 이름 변경')
        heading.setObjectName('Heading')
        outer.addWidget(heading)
        hint = QLabel('대상 선택 → 변경 방법 및 옵션 지정 → 변경 전후 미리보기 → 체크한 항목만 저장.\n'
                      '실제 ZIP·7z, 게임 설치 폴더, 모음집은 변경하지 않아. 저장 전 메타데이터를 백업해.')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        outer.addWidget(hint)
        options = QHBoxLayout()
        options.addWidget(QLabel('변경 방법'))
        self.mode = DarkMenuSelect()
        self.mode.addItem('표에서 게임별 이름 직접 수정', 'manual')
        self.mode.addItem('품번으로 작품명 조회', 'lookup')
        self.mode.addItem('이름에서 문구 찾아 바꾸기', 'replace')
        self.mode.addItem('원본 파일명으로 일괄 복원', 'original')
        self.mode.addItem('이전 이름으로 일괄 되돌리기', 'undo')
        self.mode.currentIndexChanged.connect(self.update_mode)
        options.addWidget(self.mode, 2)
        options.addWidget(QLabel('조회 언어'))
        self.language = DarkMenuSelect()
        for code, (label, _) in LANGUAGES.items():
            self.language.addItem(label, code)
        index = self.language.findData(library.settings.get('title_language', 'ko'))
        self.language.setCurrentIndex(max(index, 0))
        options.addWidget(self.language, 1)
        outer.addLayout(options)

        self.replace_row = QWidget()
        rr = QHBoxLayout(self.replace_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.addWidget(QLabel('찾기'))
        self.find_field = QLineEdit()
        self.find_field.setPlaceholderText('바꿀 문구')
        rr.addWidget(self.find_field, 2)
        rr.addWidget(QLabel('바꾸기'))
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText('새 문구 · 빈칸이면 삭제')
        rr.addWidget(self.replace_field, 2)
        self.case_sensitive = QCheckBox('대소문자 구분')
        rr.addWidget(self.case_sensitive)
        outer.addWidget(self.replace_row)
        self.keep_custom = QCheckBox('이미 수동으로 수정한 게임은 건너뛰기 (권장)')
        self.keep_custom.setChecked(True)
        outer.addWidget(self.keep_custom)
        self.localized_save = QCheckBox('품번 조회 결과를 선택 언어의 제목으로 저장 (언어 전환 유지)')
        self.localized_save.setChecked(True)
        outer.addWidget(self.localized_save)

        filter_row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('대상 게임 검색 · 이름 또는 품번')
        self.filter_edit.textChanged.connect(self.refilter)
        filter_row.addWidget(self.filter_edit, 1)
        self.scope = DarkMenuSelect()
        self.scope.addItem('모든 게임', 'all')
        self.scope.addItem('품번만 있는 게임', 'code_only')
        self.scope.addItem('품번이 있는 게임', 'with_code')
        self.scope.currentIndexChanged.connect(self.refilter)
        filter_row.addWidget(self.scope)
        select_all = QPushButton('보이는 게임 전체 선택')
        select_all.clicked.connect(lambda: self.select_visible(True))
        filter_row.addWidget(select_all)
        clear = QPushButton('선택 해제')
        clear.clicked.connect(lambda: self.select_visible(False))
        filter_row.addWidget(clear)
        outer.addLayout(filter_row)

        self.targets = QTableWidget(len(self.games), 3)
        self.targets.setHorizontalHeaderLabels(['대상', '현재 표시 이름', '작품 코드'])
        self.targets.verticalHeader().hide()
        self.targets.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.targets.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.targets.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.targets.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.targets.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.targets.setMaximumHeight(202)
        for index, game in enumerate(self.games):
            tick = QTableWidgetItem('')
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setCheckState(Qt.CheckState.Checked if game.id == initial_game_id else Qt.CheckState.Unchecked)
            tick.setData(Qt.ItemDataRole.UserRole, game.id)
            self.targets.setItem(index, 0, tick)
            title = QTableWidgetItem(self.library.title(game))
            title.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.targets.setItem(index, 1, title)
            code = QTableWidgetItem(self.library.product_code(game) or '—')
            code.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.targets.setItem(index, 2, code)
        outer.addWidget(self.targets)

        review_row = QHBoxLayout()
        self.preview_btn = QPushButton('변경 전후 미리보기')
        self.preview_btn.clicked.connect(self.create_preview)
        review_row.addWidget(self.preview_btn)
        self.progress = QLabel('이름은 미리보기를 만든 다음에만 변경할 수 있어.')
        self.progress.setObjectName('Muted')
        self.progress.setWordWrap(True)
        review_row.addWidget(self.progress, 1)
        outer.addLayout(review_row)
        self.preview_table = QTableWidget(0, 5)
        self.preview_table.setHorizontalHeaderLabels(['적용', '현재 제목', '변경할 제목 (편집 가능)', '출처', '확인 상태'])
        self.preview_table.verticalHeader().hide()
        self.preview_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.itemChanged.connect(self.preview_edited)
        outer.addWidget(self.preview_table, 1)
        footer = QHBoxLayout()
        self.confirm = QPushButton('체크한 변경 사항 저장')
        self.confirm.setObjectName('Save')
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.apply_preview)
        footer.addStretch(1)
        footer.addWidget(self.confirm)
        close = QPushButton('닫기')
        close.clicked.connect(self.request_close)
        footer.addWidget(close)
        outer.addLayout(footer)
        # A preview is tied to its exact options and selected target set.
        for field in (self.find_field, self.replace_field):
            field.textChanged.connect(lambda *_: self.clear_preview())
        self.language.currentIndexChanged.connect(lambda *_: self.clear_preview())
        self.keep_custom.toggled.connect(lambda *_: self.clear_preview())
        self.localized_save.toggled.connect(lambda *_: self.clear_preview())
        self.case_sensitive.toggled.connect(lambda *_: self.clear_preview())
        self.targets.itemChanged.connect(lambda *_: self.clear_preview())
        self.update_mode()

    def update_mode(self, *_args):
        lookup = self.mode.currentData() == 'lookup'
        self.language.setEnabled(lookup)
        self.localized_save.setVisible(lookup)
        self.keep_custom.setChecked(self.mode.currentData() in ('lookup', 'replace'))
        self.replace_row.setVisible(self.mode.currentData() == 'replace')
        self.clear_preview()

    def clear_preview(self):
        self.preview_items = {}
        self.preview_table.setRowCount(0)
        self.confirm.setEnabled(False)

    def refilter(self, *_args):
        query = self.filter_edit.text().casefold().strip()
        scope = self.scope.currentData()
        from localized_titles import is_code_only_title
        for i, game in enumerate(self.games):
            matched = (not query or query in (self.library.title(game) + ' ' + game.name + ' ' +
                            self.library.product_code(game)).casefold())
            if scope == 'code_only':
                matched = matched and is_code_only_title(game.name)
            if scope == 'with_code':
                matched = matched and bool(self.library.product_code(game))
            self.targets.setRowHidden(i, not matched)
        self.clear_preview()

    def select_visible(self, checked: bool):
        for i in range(self.targets.rowCount()):
            if not self.targets.isRowHidden(i):
                self.targets.item(i, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.clear_preview()

    def selected_games(self):
        return [game for i, game in enumerate(self.games)
                if self.targets.item(i, 0).checkState() == Qt.CheckState.Checked]

    def create_preview(self):
        if self.worker is not None:
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 완료된 결과만 미리보기에 표시할게.')
            return
        self.clear_preview()
        games = self.selected_games()
        if not games:
            QMessageBox.information(self, '대상 없음', '변경할 게임을 먼저 체크해 주세요.')
            return
        games = self.bulk_actions.eligible_games(
            games, skip_custom=self.keep_custom.isChecked())
        if not games:
            QMessageBox.information(self, '대상 없음', '수동 수정된 이름을 제외하면 남는 게임이 없어.')
            return
        mode = self.mode.currentData()
        if mode == 'lookup':
            entries = [
                (g.id, self.library.title(g), identity[1], identity[0])
                for g in games
                if (identity := explicit_work_identity(self.library, g))
            ]
            if not entries:
                QMessageBox.information(self, '품번 없음', '조회 가능한 DLsite 품번 또는 Steam App ID가 없어.')
                return
            if QMessageBox.question(self, '품번 일괄 조회',
                    f'{len(entries)}개 작품을 PlayDock DB에서 먼저 조회할까요?\n'
                    'DB에 저장되지 않은 작품만 인터넷에서 추가 확인합니다.\n'
                    '결과를 보여주고 선택하기 전까지 어떤 게임명도 변경하지 않아.') != QMessageBox.StandardButton.Yes:
                return
            self.worker = BulkTitleWorker(entries, self.language.currentData() or 'ko',
                                          self.library.store / 'localized_product_titles.json')
            self.worker.progress.connect(self.on_progress)
            self.worker.complete.connect(self.show_lookup_preview)
            self.worker.finished.connect(self.worker_finished)
            self.preview_btn.setText('조회 중단')
            self.progress.setText(f'{len(entries)}개 작품명 조회 중…')
            self.worker.start()
            return
        try:
            records = self.bulk_actions.preview_changes(
                games, mode, find=self.find_field.text(),
                replacement=self.replace_field.text(),
                case_sensitive=self.case_sensitive.isChecked())
        except ValueError as exc:
            QMessageBox.warning(self, '변경 규칙 오류', str(exc))
            return
        self.set_preview_records(records, check_default=mode != 'manual')

    def on_progress(self, done, total, code):
        self.progress.setText(f'조회 진행 {done}/{total} · {code}')

    def show_lookup_preview(self, rows):
        language = self.language.currentData() or 'ko'
        records = self.bulk_actions.lookup_preview(
            self.games, rows, language,
            save_as_localized=self.localized_save.isChecked())
        self.set_preview_records(records, requested_language=language)

    def set_preview_records(self, records, requested_language='ko', check_default=True):
        self.preview_items = {r.game_id: r for r in records}
        self.preview_table.blockSignals(True)
        self.preview_table.setRowCount(len(records))
        for i, record in enumerate(records):
            is_valid = bool(record.proposed_name)
            is_fallback = record.method == 'localized' and record.language != requested_language
            tick = QTableWidgetItem('')
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setCheckState(Qt.CheckState.Checked if check_default and is_valid and not is_fallback else Qt.CheckState.Unchecked)
            tick.setData(Qt.ItemDataRole.UserRole, record.game_id)
            self.preview_table.setItem(i, 0, tick)
            old = QTableWidgetItem(record.expected_name)
            old.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.preview_table.setItem(i, 1, old)
            proposed = QTableWidgetItem(record.proposed_name)
            editable = record.method not in ('original', 'undo')
            proposed.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                              (Qt.ItemFlag.ItemIsEditable if editable else Qt.ItemFlag(0)))
            self.preview_table.setItem(i, 2, proposed)
            origin = QTableWidgetItem(record.source or '사용자 지정')
            origin.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.preview_table.setItem(i, 3, origin)
            status = QTableWidgetItem('다른 언어 · 확인 필요' if is_fallback else
                                      ('미리보기 확인' if is_valid else '조회 실패 / 직접 입력 가능'))
            status.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.preview_table.setItem(i, 4, status)
            self.preview_table.setRowHeight(i, 37)
        self.preview_table.blockSignals(False)
        self.confirm.setEnabled(bool(records))
        self.progress.setText(f'{len(records)}개 미리보기 생성 · 체크한 행만 저장돼. 결과 제목은 직접 수정 가능해.')

    def preview_edited(self, item):
        if item.column() == 2:
            self.preview_table.item(item.row(), 0).setCheckState(Qt.CheckState.Checked)

    def apply_preview(self):
        if self.worker is not None:
            return
        approved_edits = []
        for i in range(self.preview_table.rowCount()):
            if self.preview_table.item(i, 0).checkState() != Qt.CheckState.Checked:
                continue
            key = self.preview_table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            original = self.preview_items.get(key)
            if original is None:
                continue
            title = self.preview_table.item(i, 2).text()
            approved_edits.append((original, title))
        changes = self.bulk_actions.prepare_changes(
            approved_edits, self.language.currentData() or 'ko')
        if not changes:
            QMessageBox.information(self, '선택 없음', '저장할 변경 사항을 체크해 주세요.')
            return
        if QMessageBox.question(self, '일괄 이름 저장 확인',
                f'{len(changes)}개 게임의 표시 이름을 변경할까요?\n'
                '저장 전에 메타데이터 ZIP 백업을 만들고, 게임별 이전 이름 이력에도 기록해.\n'
                '실제 압축파일/설치 폴더는 변경하지 않아.') != QMessageBox.StandardButton.Yes:
            return
        try:
            total, backup = self.bulk_actions.apply_changes(self.games, changes)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, '일괄 저장 실패', str(exc))
            return
        QMessageBox.information(self, '일괄 변경 완료',
                    f'{total}개 게임 이름 변경 완료.\n백업: {backup}\n'
                    '원본 파일은 그대로이며, 본체에서 새로고침하면 적용돼.')
        self.accept()

    def worker_finished(self):
        self.worker = None
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText('변경 전후 미리보기')

    def request_close(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 작업이 끝나면 닫아 줘.')
            return
        self.reject()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 작업이 끝나면 닫아 줘.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 완료되면 창을 닫을 수 있어.')
            event.ignore()
            return
        super().closeEvent(event)

