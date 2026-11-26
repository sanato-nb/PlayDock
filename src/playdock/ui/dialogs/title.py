"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
)

from core import Library
from database.work_repository import WorkDatabase
from services.bulk_title_service import BulkTitleActions
from services.localized_titles import LANGUAGES, is_code_only_title, normalize_title_priority
from ui.selectors import DarkMenuSelect
from ui.widgets.table_checks import StatusCheckDelegate
from ui.widgets.buttons import configure_action_button


from workers.title import BulkTitleWorker


class BulkTitleSettingsDialog(QDialog):
    """Detailed bulk rename: scope -> source -> editable preview -> explicit apply."""

    def __init__(self, library: Library, games, initial_game_id=None, parent=None):
        super().__init__(parent)
        self.library = library
        self.bulk_actions = BulkTitleActions(library)
        self.games = list(games)
        self.worker = None
        self.preview_items = {}
        self._games_by_id = {game.id: game for game in self.games}
        self._preview_revision = 0
        self._lookup_revision = None
        self.setWindowTitle('일괄 이름 변경 · 상세 설정')
        self.resize(1130, 780)
        self.setMinimumSize(850, 640)
        outer = QVBoxLayout(self)
        heading = QLabel('일괄 게임 이름 변경')
        heading.setObjectName('Heading')
        outer.addWidget(heading)
        hint = QLabel('공식 게임명은 게임 정보 수집에서 확인한 작품에만 적용할 수 있습니다.\n'
                      '직접 수정과 원본 이름 복원은 수집 전에도 가능합니다. 실제 압축파일명은 변경하지 않습니다.')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        outer.addWidget(hint)
        if initial_game_id is not None:
            chosen = next((g for g in self.games if g.id == initial_game_id), None)
            if chosen is not None and chosen.archive is not None:
                first_name = self.library.meta(chosen).get(
                    "original_archive_name"
                ) or chosen.archive.name
                original_note = QLabel(f"최초 압축파일명 (복원용): {first_name}")
                original_note.setObjectName("Muted")
                original_note.setWordWrap(True)
                outer.addWidget(original_note)
        options = QHBoxLayout()
        options.addWidget(QLabel('변경 방법'))
        self.mode = DarkMenuSelect()
        self.mode.addItem('표에서 게임별 이름 직접 수정', 'manual')
        self.mode.addItem('공식 게임명 적용 (수집한 DB)', 'lookup')
        self.mode.addItem('이름에서 문구 찾아 바꾸기', 'replace')
        self.mode.addItem('최초 압축파일 이름으로 표시 이름 복원', 'original')
        self.mode.addItem('이전 이름으로 일괄 되돌리기', 'undo')
        self.mode.currentIndexChanged.connect(self.update_mode)
        options.addWidget(self.mode, 2)
        options.addWidget(QLabel('언어 우선순위'))
        self.language = DarkMenuSelect()
        self._priority_orders = {
            'ko': ('ko', 'ja', 'en'), 'ja': ('ja', 'ko', 'en'), 'en': ('en', 'ko', 'ja'),
            'ko,en,ja': ('ko', 'en', 'ja'), 'ja,en,ko': ('ja', 'en', 'ko'),
            'en,ja,ko': ('en', 'ja', 'ko'),
        }
        labels = {'ko': '한국어', 'ja': '일본어', 'en': '영어'}
        for key, order in self._priority_orders.items():
            self.language.addItem(' → '.join(labels[lang] for lang in order), key)
        index = self.language.findData(library.settings.get('bulk_title_priority', 'ko'))
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
        self.localized_save = QCheckBox('확인된 모든 언어 제목 저장 (언어 전환 유지)')
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
        select_all = QPushButton('전체 선택')
        select_all.clicked.connect(lambda: self.select_visible(True))
        filter_row.addWidget(select_all)
        clear = QPushButton('선택 해제')
        clear.clicked.connect(lambda: self.select_visible(False))
        filter_row.addWidget(clear)
        outer.addLayout(filter_row)

        self.targets = QTableWidget(len(self.games), 3)
        self.targets.setHorizontalHeaderLabels(['대상', '현재 표시 이름', '작품 코드'])
        self.targets.setItemDelegateForColumn(0, StatusCheckDelegate(self.targets))
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
        self.progress = QLabel('변경 전후 미리보기를 확인한 후 이름을 변경할 수 있습니다.')
        self.progress.setObjectName('Muted')
        self.progress.setWordWrap(True)
        review_row.addWidget(self.progress, 1)
        outer.addLayout(review_row)
        self.preview_table = QTableWidget(0, 6)
        self.preview_table.setHorizontalHeaderLabels(['적용', '현재 제목', '변경할 제목 (편집 가능)', '출처', '확인 상태', '적용 후 표시'])
        self.preview_table.setItemDelegateForColumn(0, StatusCheckDelegate(self.preview_table))
        self.preview_table.verticalHeader().hide()
        self.preview_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.preview_table.itemChanged.connect(self.preview_edited)
        outer.addWidget(self.preview_table, 1)
        footer = QHBoxLayout()
        self.confirm = QPushButton('적용')
        configure_action_button(self.confirm, 'Save')
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

    def title_priority(self):
        return self._priority_orders.get(self.language.currentData(), ('ko', 'ja', 'en'))

    def update_mode(self, *_args):
        lookup = self.mode.currentData() == 'lookup'
        self.language.setEnabled(lookup)
        self.localized_save.setVisible(lookup)
        self.keep_custom.setChecked(self.mode.currentData() in ('lookup', 'replace'))
        self.replace_row.setVisible(self.mode.currentData() == 'replace')
        self.clear_preview()

    def clear_preview(self):
        self._preview_revision += 1
        self.preview_items = {}
        self.preview_table.setRowCount(0)
        self.confirm.setEnabled(False)

    def refilter(self, *_args):
        query = self.filter_edit.text().casefold().strip()
        scope = self.scope.currentData()
        from services.localized_titles import is_code_only_title
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
        previous = self.targets.blockSignals(True)
        try:
            for i in range(self.targets.rowCount()):
                if not self.targets.isRowHidden(i):
                    self.targets.item(i, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            self.targets.blockSignals(previous)
        self.clear_preview()

    def selected_games(self):
        return [game for i, game in enumerate(self.games)
                if not self.targets.isRowHidden(i) and
                self.targets.item(i, 0).checkState() == Qt.CheckState.Checked]

    def create_preview(self):
        if self.worker is not None:
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 완료된 결과만 미리보기에 표시합니다.')
            return
        self.clear_preview()
        games = self.selected_games()
        if not games:
            QMessageBox.information(self, '대상 없음', '변경할 게임을 먼저 선택해 주세요.')
            return
        games = self.bulk_actions.eligible_games(
            games, skip_custom=self.keep_custom.isChecked())
        if not games:
            QMessageBox.information(self, '대상 없음', '수동으로 수정한 게임을 제외하면 변경할 대상이 없습니다.')
            return
        mode = self.mode.currentData()
        if mode == 'lookup':
            db = WorkDatabase(self.library.store)
            # Read verified links once for this preview; the worker reuses
            # the same official records, not a second per-game DB lookup.
            linked = db.get_linked_official_works(game.id for game in games)
            entries = []
            verified_records = {}
            for game in games:
                record = linked.get(game.id)
                if not record:
                    continue
                code, store = record["code"], record["store"]
                entries.append((game.id, self.library.title(game), code, store))
                verified_records[(store, code)] = record
            if not entries:
                QMessageBox.information(
                    self, '공식 게임 정보 없음',
                    "선택한 게임에 저장된 공식 작품 연결이 없습니다.\n"
                    "먼저 PlayDock에서 '게임 정보 수집'을 실행하세요.\n"
                    "직접 수정과 원본 이름 복원은 그대로 이용할 수 있습니다.",
                )
                return
            if QMessageBox.question(self, '공식 게임명 적용',
                    f'{len(entries)}개 게임의 공식 작품명을 PlayDock DB에서 가져올까요?\n'
                    '인터넷에서 다시 검색하지 않으며, 미리보기에서 선택한 항목만 저장합니다.'
                    ) != QMessageBox.StandardButton.Yes:
                return
            self._lookup_revision = self._preview_revision
            self.worker = BulkTitleWorker(
                entries, self.title_priority()[0],
                self.library.store / 'localized_product_titles.json',
                db_only=True, verified_records=verified_records, priority=self.title_priority(),
            )
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
        if self._lookup_revision != self._preview_revision:
            self.progress.setText('조회 중 설정이 변경됐습니다. 다시 미리보기를 만들어 주세요.')
            return
        language = self.title_priority()[0]
        records = self.bulk_actions.lookup_preview(
            self.games, rows, language,
            save_as_localized=self.localized_save.isChecked())
        self.set_preview_records(records, requested_language=language)

    def set_preview_records(self, records, requested_language='ko', check_default=True):
        self.preview_items = {r.game_id: r for r in records}
        self.preview_table.blockSignals(True)
        self.preview_table.setRowCount(len(records))
        for i, record in enumerate(records):
            status_text, is_valid = self.bulk_actions.preview_status(
                self._games_by_id.get(record.game_id), record, record.proposed_name, requested_language)
            tick = QTableWidgetItem('')
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setCheckState(Qt.CheckState.Checked if check_default and is_valid else Qt.CheckState.Unchecked)
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
            status = QTableWidgetItem(status_text)
            status.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.preview_table.setItem(i, 4, status)
            final_name = QTableWidgetItem(self.bulk_actions.preview_display(
                self._games_by_id.get(record.game_id), record, record.proposed_name, requested_language))
            final_name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.preview_table.setItem(i, 5, final_name)
            self.preview_table.setRowHeight(i, 37)
        self.preview_table.blockSignals(False)
        self.update_apply_state()

    def update_apply_state(self):
        count = sum(self.preview_table.item(i, 0).checkState() == Qt.CheckState.Checked
                    for i in range(self.preview_table.rowCount()))
        self.confirm.setEnabled(count > 0 and self.worker is None)
        self.progress.setText(f'미리보기 {self.preview_table.rowCount()}개 · 적용 선택 {count}개. 제목을 직접 수정할 수 있습니다.')

    def preview_edited(self, item):
        if item.column() == 2:
            tick = self.preview_table.item(item.row(), 0)
            original = self.preview_items.get(tick.data(Qt.ItemDataRole.UserRole))
            if original is None:
                return
            status, valid = self.bulk_actions.preview_status(
                self._games_by_id.get(original.game_id), original, item.text(),
                self.title_priority()[0])
            previous = self.preview_table.blockSignals(True)
            try:
                self.preview_table.item(item.row(), 4).setText(status)
                self.preview_table.item(item.row(), 5).setText(self.bulk_actions.preview_display(
                    self._games_by_id.get(original.game_id), original, item.text(),
                    self.title_priority()[0]))
                tick.setCheckState(Qt.CheckState.Checked if valid else Qt.CheckState.Unchecked)
            finally:
                self.preview_table.blockSignals(previous)
        if item.column() in (0, 2):
            self.update_apply_state()

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
            approved_edits, self.title_priority()[0])
        if not changes:
            QMessageBox.information(self, '선택 없음', '저장할 변경 사항을 선택해 주세요.')
            return
        checked_count = len(changes)
        changes, rejected = self.bulk_actions.partition_changes(self.games, changes)
        skipped = len(rejected)
        details = "\n".join(f"• {change.expected_name}: {reason}" for change, reason in rejected[:10])
        if skipped > 10:
            details += f"\n외 {skipped - 10}개"
        if not changes:
            QMessageBox.warning(self, '적용할 수 있는 이름 없음', details)
            return
        message = (f'{checked_count}개 선택 · {len(changes)}개 적용 가능 · {skipped}개 제외\n'
                   '공식 제목은 확인된 언어와 선택한 우선순위에 따라 적용합니다.\n'
                   '적용 전에 메타데이터를 ZIP으로 백업합니다. 실제 게임 파일은 변경하지 않습니다.')
        if skipped:
            message += "\n\n제외 이유:\n" + details
        if QMessageBox.question(self, '일괄 이름 적용 확인', message) != QMessageBox.StandardButton.Yes:
            return
        try:
            total, backup = self.bulk_actions.apply_changes(self.games, changes)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, '일괄 저장 실패', str(exc))
            return
        result = (f'적용 완료 {total}개 · 변경 없음 {len(changes) - total}개 · 제외 {skipped}개\n'
                  f'백업: {backup}\n원본 파일은 그대로 유지됩니다.')
        if skipped:
            result += "\n\n제외 이유:\n" + details
        if self.mode.currentData() == 'lookup' and total:
            self.library.settings['bulk_title_priority'] = self.language.currentData()
            try:
                self.library.save_settings()
            except OSError:
                result += "\n우선순위 기본값 저장 실패 · 게임 이름은 적용되었습니다."
        QMessageBox.information(self, '일괄 변경 완료', result)
        self.accept()

    def worker_finished(self):
        self.worker = None
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText('변경 전후 미리보기')
        if self.preview_table.rowCount():
            self.update_apply_state()

    def request_close(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 작업이 끝난 후 창을 닫아 주세요.')
            return
        self.reject()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 작업이 끝난 후 창을 닫아 주세요.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.progress.setText('조회 중단 요청 중… 작업이 끝나면 창을 닫을 수 있습니다.')
            event.ignore()
            return
        super().closeEvent(event)
