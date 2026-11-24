"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

from urllib.parse import urlencode

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QDialog

from simple_title_edit import (
    save_display_title,
    undo_display_title,
    restore_filename_title,
    title_history,
)
from game_codes import normalize_code
from artwork import get_secret
from ai_providers import PROVIDERS, current_provider, current_models
from localized_titles import LANGUAGES, is_code_only_title


from services.title_workers import TitleWorker, BulkTitleWorker
from ui.dialogs.title import BulkPreviewDialog, KoreanWebCandidatesDialog, BulkTitleSettingsDialog


class TitleEditorActionsMixin:
    """Title editor events, lookup coordination and metadata changes."""

    def toggle_mode(self):
        """Keep the full detailed editor, but default to one-field editing."""
        advanced = self.panel_stack.currentIndex() == 0
        self.panel_stack.setCurrentIndex(1 if advanced else 0)
        self.mode_btn.setText('간편 수정으로 돌아가기' if advanced else '상세 기능 보기')
        for widget in (self.language_header, self.language_menu, self.bulk_btn):
            widget.setVisible(advanced)


    def open_korean_title_search(self):
        # Browser fallback for blocked meta-search. Never saves a title.
        game = self.current_game()
        if not game:
            return
        code = self.code_input.text().strip().upper()
        term = code if code else self.library.base_title(game)
        query = term + ' 한국어 게임 제목'
        url = 'https://www.google.com/search?' + urlencode({'q': query})
        QDesktopServices.openUrl(QUrl(url))


    def open_korean_lookup_from_simple(self):
        """Jump to the original detailed editor, then search public Korean names."""
        if self.panel_stack.currentIndex() == 0:
            self.toggle_mode()
        self.start_lookup('korean_web')


    def simple_preview_changed(self, text: str):
        game = self.current_game()
        if not game:
            self.simple_preview.clear()
            return
        from game_codes import title_with_code
        preview = title_with_code(text.strip() or game.name, self.library.product_code(game))
        self.simple_preview.setText('저장 후 표시: ' + preview)
        changed = text.strip() != self.library.base_title(game)
        self.simple_save_btn.setEnabled(bool(text.strip()) and changed and self.worker is None)


    def update_simple_history(self):
        game = self.current_game()
        if game is None:
            self.history_label.setText('저장된 이전 이름이 없습니다.')
            return
        history = title_history(self.library, game)
        if not history:
            self.history_label.setText('저장된 이전 이름이 없습니다.')
            return
        previous = history[-1]
        # A localized title may have been visible before a manual override.
        if previous.get('prefer_manual_title'):
            label = previous.get('title') or game.name
        else:
            meta = self.library.meta(game)
            from localized_titles import localized_title_for
            previous_meta = dict(meta, **previous)
            label = localized_title_for(previous_meta, self.library.settings,
                original_name=game.name, product_code=self.library.product_code(game)) or previous.get('title') or game.name
        self.history_label.setText(f'이전 이름: {label}  ·  저장 이력 {len(history)}개')


    def save_simple_title(self):
        game = self.current_game()
        if not game or self.worker is not None:
            return
        try:
            changed = save_display_title(self.library, game, self.simple_edit.text())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '이름 저장 실패', str(exc))
            return
        if not changed:
            self.status.setText('이미 같은 이름으로 표시되고 있어.')
            return
        self.refresh()
        self.status.setText('이름 저장 완료. 기존 게임·압축파일은 변경하지 않았어. 이전 이름은 되돌릴 수 있어.')


    def undo_simple_title(self):
        game = self.current_game()
        if not game or self.worker is not None:
            return
        try:
            changed = undo_display_title(self.library, game)
        except OSError as exc:
            QMessageBox.warning(self, '이름 복원 실패', str(exc))
            return
        if changed:
            self.refresh()
            self.status.setText('이전 이름으로 되돌렸어. 변경 내용은 자동 저장됐어.')
        else:
            self.status.setText('되돌릴 이전 이름이 없어.')


    def restore_simple_original(self):
        game = self.current_game()
        if not game or self.worker is not None:
            return
        if QMessageBox.question(self, '원본 이름으로 복원',
                f'이 게임의 표시 이름을 원본으로 바꿀까요?\n\n{game.name}\n\n'
                '원본 압축파일은 변경되지 않고, 이 작업도 되돌릴 수 있어.') != QMessageBox.StandardButton.Yes:
            return
        try:
            changed = restore_filename_title(self.library, game)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '이름 복원 실패', str(exc))
            return
        if changed:
            self.refresh()
            self.status.setText('원본 파일명으로 표시되도록 복원했어. 필요하면 이전 이름으로 되돌릴 수 있어.')


    def set_enabled(self, enabled: bool):
        busy = self.worker is not None
        self.simple_edit.setEnabled(enabled and not busy)
        self.simple_save_btn.setEnabled(enabled and not busy)
        self.simple_korean_btn.setEnabled(enabled and not busy)
        game = self.current_game() if enabled else None
        self.simple_undo_btn.setEnabled(bool(game and title_history(self.library, game)) and not busy)
        self.simple_original_btn.setEnabled(bool(game and self.library.base_title(game) != game.name) and not busy)
        self.edit.setEnabled(enabled and not busy)
        self.localized_edit.setEnabled(enabled and not busy)
        self.game_language_menu.setEnabled(enabled and not busy)
        self.game_language_save.setEnabled(enabled and not busy)
        self.localized_lookup_btn.setEnabled(enabled and not busy and bool(self.code_input.text().strip()))
        self.localized_save_btn.setEnabled(enabled and not busy)
        self.translate_btn.setEnabled(enabled and not busy)
        self.korean_web_btn.setEnabled(enabled and not busy)
        self.korean_browser_btn.setEnabled(enabled and not busy)
        self.bulk_settings_btn.setEnabled(not busy and self.bulk_worker is None)
        self.bulk_btn.setEnabled(not busy)
        self.bulk_btn.setText('조회 중단' if self.bulk_worker is not None else '품번만 있는 게임 일괄 조회')
        self.lookup_btn.setEnabled(enabled and not busy and bool(self.code_input.text().strip()))
        self.code_input.setEnabled(enabled and not busy)
        self.code_save_btn.setEnabled(enabled and not busy)
        self.gpt_btn.setEnabled(enabled and not busy)
        self.reset_btn.setEnabled(enabled and not busy)
        self.save_btn.setEnabled(enabled and not busy)


    def current_game(self):
        return next((g for g in self.games if g.id == self.selected_id), None)


    def current_code(self):
        game = self.current_game()
        return self.library.product_code(game) if game else None


    def refresh(self):
        keep = self.selected_id
        self.games = self.library.scan()
        self.selected_id = keep
        self.populate()
        self.status.setText(f'게임 {len(self.games)}개를 읽었습니다. 이름을 바꾼 뒤 본체에서 새로고침하세요.')


    def populate(self):
        query = self.search.text().casefold().strip()
        keep = self.selected_id
        self.games_list.blockSignals(True)
        self.games_list.clear()
        chosen = None
        for game in self.games:
            title = self.library.title(game)
            archive = game.archive.name if game.archive else ''
            if query and query not in (title + ' ' + game.name + ' ' + archive).casefold():
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            self.games_list.addItem(item)
            if keep == game.id:
                chosen = item
        self.count.setText(f'표시 {self.games_list.count()}개 / 전체 {len(self.games)}개')
        if chosen is None and self.games_list.count():
            chosen = self.games_list.item(0)
        if chosen is not None:
            self.games_list.setCurrentItem(chosen)
        else:
            self.games_list.setCurrentRow(-1)
        self.games_list.blockSignals(False)
        self.select_game(chosen)


    def select_game(self, item, _previous=None):
        new_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.selected_id = new_id
        game = self.current_game()
        if not game:
            self.simple_current.setText('왼쪽에서 게임을 선택하세요')
            self.simple_edit.blockSignals(True)
            self.simple_edit.clear()
            self.simple_edit.blockSignals(False)
            self.simple_preview.clear()
            self.history_label.setText('저장된 이전 이름이 없습니다.')
            self.original.setText('게임을 선택하세요')
            self.edit.clear()
            self.localized_edit.clear()
            self.code_input.clear()
            self.file_detail.clear()
            self.set_enabled(False)
            return
        title = self.library.title(game)
        self.simple_current.setText(title)
        self.simple_edit.blockSignals(True)
        # Don't place the automatic [RJ...] decoration in the input: it is
        # added during display and must not be duplicated in metadata.
        self.simple_edit.setText(self.library.base_title(game))
        self.simple_edit.blockSignals(False)
        self.update_simple_history()
        self.simple_preview_changed(self.simple_edit.text())
        self.original.setText(title)
        self.file_detail.setText('원본: ' + (game.archive.name if game.archive else game.name)
                                 + '\n작품 코드: ' + (self.current_code() or '없음'))
        meta = self.library.meta(game)
        personal_lang = meta.get('title_language') or ''
        personal_idx = self.game_language_menu.findData(personal_lang)
        self.game_language_menu.setCurrentIndex(max(0, personal_idx))
        language = self.language_menu.currentData() or 'ko'
        localized = meta.get('localized_titles') or {}
        localized = localized if isinstance(localized, dict) else {}
        self._loading_localized = True
        self.localized_edit.setText(str(localized.get(language) or ''))
        self._loading_localized = False
        self.localized_candidate_language = language
        self.localized_source = str((meta.get('localized_sources') or {}).get(language) or '사용자 입력')
        self.edit.setText(str(meta.get('title') or game.name))
        self.code_input.setText(self.library.product_code(game))
        self.suggestion_source = '수동 수정'
        self.suggestion_code = ''
        self.source.setText('직접 수정하거나 작품 코드를 조회하세요. 조회 결과는 자동 저장되지 않습니다.')
        self.set_enabled(True)


    def start_lookup(self, mode: str):
        game = self.current_game()
        if game is None or self.worker is not None:
            return
        try:
            code = normalize_code(self.code_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, '품번 오류', str(exc))
            return
        if mode in ('rj', 'localized') and not code:
            QMessageBox.information(self, '품번 없음', '이 게임에 RJ/VJ/BJ/EJ 코드가 없습니다.')
            return
        provider = current_provider(self.library)
        model, _image_model = current_models(self.library, provider)
        if mode in ('gpt', 'translate'):
            # Refresh configuration saved by the independent launcher without
            # discarding unsaved title edits (only settings.json is reloaded).
            from core import load_json
            fresh = load_json(self.library.config_path)
            if fresh:
                self.library.settings.update({k: fresh[k] for k in ('ai_provider', 'ai_models') if k in fresh})
                provider = current_provider(self.library)
                model, _image_model = current_models(self.library, provider)
            if provider != 'ollama' and not get_secret(provider):
                QMessageBox.information(self, 'API 키 필요',
                    f"PlayDock의 AI 설정에서 {PROVIDERS[provider]['name']} 키를 등록하세요.")
                return
            if QMessageBox.question(self, 'AI 서비스 사용 안내',
                f"{PROVIDERS[provider]['name']}의 {model} 모델을 사용합니다. API 비용이 발생할 수 있습니다. 계속할까요?") != QMessageBox.StandardButton.Yes:
                return
        if mode == 'translate':
            source_title = self.localized_edit.text().strip()
            if not source_title:
                QMessageBox.information(self, '번역할 제목 없음',
                    '먼저 품번으로 원제 제목을 조회한 뒤 AI 번역을 눌러 주세요.')
                return
        elif mode == 'korean_web':
            variants = self.library.meta(game).get('localized_titles') or {}
            original_japanese = variants.get('ja') if isinstance(variants, dict) else ''
            source_title = (original_japanese or self.localized_edit.text().strip()
                            or self.library.base_title(game))
        else:
            source_title = self.library.base_title(game)
        self.worker = TitleWorker(game.id, source_title, code,
                                  self.library.store / ('localized_product_titles.json' if mode == 'localized' else 'product_titles.json'), mode, provider, model,
                                  self.language_menu.currentData() or 'ko')
        self.worker.found.connect(self.lookup_found)
        self.worker.localized_found.connect(self.lookup_localized_found)
        self.worker.korean_web_found.connect(self.lookup_korean_web_found)
        self.worker.failed.connect(self.lookup_failed)
        self.worker.finished.connect(self.lookup_finished)
        self.set_enabled(True)
        if mode == 'korean_web':
            self.status.setText('공개 웹페이지에서 실제 한국어 제목을 검색하는 중... (AI 번역 없음)')
        elif mode in ('rj', 'localized'):
            self.status.setText('작품 코드의 공개 정보를 조회 중...')
        else:
            self.status.setText(f'{PROVIDERS[provider]["name"]}에서 이름을 추천받는 중...')
        self.worker.start()


    def lookup_found(self, game_id: str, candidate: str, source: str, code: str):
        if game_id != self.selected_id:
            self.status.setText('다른 게임이 선택되어 결과를 적용하지 않았습니다.')
            return
        self.edit.setText(candidate)
        self.suggestion_source = source
        self.suggestion_code = code
        if code:
            self.code_input.setText(code)
        self.source.setText('정보 출처: ' + ('DLsite 공개 정보' if 'dlsite.com' in source else source)
                            + '\n제목을 확인하고 “표시 이름 저장”을 눌러 적용하세요.')
        self.status.setText('후보를 확인했습니다. 아직 저장하지 않았습니다.')


    def lookup_failed(self, game_id: str, error: str):
        self.status.setText('조회 실패: ' + error)
        if game_id == self.selected_id:
            QMessageBox.warning(self, '제목 조회 실패', error + '\n기존 표시 이름은 유지됩니다.')


    def lookup_finished(self):
        self.worker = None
        self.set_enabled(self.current_game() is not None)


    def change_language(self, _index: int):
        language = self.language_menu.currentData() or 'ko'
        self.library.settings['title_language'] = language
        self.library.save_settings()
        self.populate()
        self.status.setText(f'기본 게임 이름 언어: {LANGUAGES[language][0]}. 본체에서 새로고침하면 반영돼.')


    def localized_manually_edited(self, _text: str):
        if self._loading_localized:
            return
        self.localized_candidate_language = self.language_menu.currentData() or 'ko'
        self.localized_source = '사용자 입력 / 직접 수정'


    def lookup_korean_web_found(self, game_id: str, candidates):
        if game_id != self.selected_id:
            self.status.setText('게임 선택이 변경되어 검색 결과를 적용하지 않았습니다.')
            return
        if not candidates:
            self.status.setText('품번과 연결된 한국어 제목 검색 결과가 없습니다. 기존 제목은 유지됩니다.')
            self.source.setText('한국어 웹 제목을 찾지 못했어요. 원제를 직접 확인하거나 수동으로 입력할 수 있어요.')
            return
        dialog = KoreanWebCandidatesDialog(candidates, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.status.setText('한국어 제목 선택을 취소했습니다. 기존 이름은 유지됩니다.')
            return
        selected = dialog.selected_candidate()
        if selected is None:
            return
        # Deliberately only fill the editor field; the user must still click
        # '이 언어의 제목 저장'. Existing locale variants remain untouched.
        self._loading_localized = True
        self.localized_edit.setText(dialog.title_result())
        self._loading_localized = False
        self.localized_candidate_language = 'ko'
        self.localized_source = '사용자가 선택한 웹 검색 후보 (공식 확인 필요): ' + selected.url
        self.source.setText(f'한국어 웹 검색 후보: {selected.url}\n'
                            '아직 저장되지 않았습니다. 출처를 확인한 뒤 “이 언어의 제목 저장”을 눌러 주세요.')
        self.status.setText('한국어 제목 후보를 선택했어. 저장 버튼을 눌러야 게임명에 반영돼.')


    def lookup_localized_found(self, game_id: str, title: str, source: str,
                               code: str, language: str):
        if game_id != self.selected_id:
            self.status.setText('다른 게임이 선택되어 결과를 적용하지 않았습니다.')
            return
        self.localized_edit.setText(title)
        self.localized_candidate_language = language
        self.localized_source = source
        selected = self.language_menu.currentData() or 'ko'
        if selected != language:
            self.source.setText(f'선택 언어의 제목이 확인되지 않아 {LANGUAGES[language][0]} 제목을 찾았어.\n'
                                '이대로 저장하면 실제 언어에 보관해. 직접 한국어로 수정하면 한국어 제목으로 저장할 수 있어.\n'
                                '조회 출처: ' + source)
        else:
            self.source.setText('조회한 작품명: ' + source + '\n확인한 뒤 언어별 제목 저장을 눌러 적용해.')
        self.status.setText('언어별 제목 후보를 찾았어. 아직 게임 이름은 변경하지 않았어.')


    def save_game_language(self):
        game = self.current_game()
        if game is None or self.worker is not None:
            return
        lang = self.game_language_menu.currentData() or ''
        self.library.update_meta(game, title_language=lang)
        self.refresh()
        if lang:
            self.status.setText(f'이 게임은 {LANGUAGES[lang][0]} 제목을 우선 표시해. 없는 경우 기존 이름으로 대체돼.')
        else:
            self.status.setText('이 게임은 전체 기본 언어 설정을 따르도록 변경했어.')


    def save_localized_title(self):
        game = self.current_game()
        if game is None or self.worker is not None:
            return
        value = self.localized_edit.text().strip()
        from product_titles import clean_title
        if not clean_title(value):
            QMessageBox.warning(self, '제목 오류', '2~240자의 올바른 게임 제목을 입력하세요.')
            return
        language = self.localized_candidate_language
        meta = self.library.meta(game)
        variants = dict(meta.get('localized_titles') or {})
        sources = dict(meta.get('localized_sources') or {})
        variants[language] = value
        sources[language] = self.localized_source
        self.library.update_meta(game, localized_titles=variants, localized_sources=sources,
                                 prefer_manual_title=False)
        self.refresh()
        preferred = self.language_menu.currentData() or 'ko'
        if preferred != language:
            self.status.setText(f'{LANGUAGES[language][0]} 원제를 저장했어. {LANGUAGES[preferred][0]} 제목은 미확인 상태야.')
        else:
            self.status.setText(f'{LANGUAGES[language][0]} 제목을 저장했어. 본체에서 새로고침하면 반영돼.')


    def open_bulk_settings(self):
        if self.worker is not None or self.bulk_worker is not None:
            QMessageBox.information(self, '조회 중', '현재 이름 조회가 끝난 뒤 시도해 주세요.')
            return
        dialog = BulkTitleSettingsDialog(self.library, self.games, self.selected_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.status.setText('일괄 이름 변경을 반영했어. 본체를 새로고침하면 표시돼.')


    def bulk_lookup(self):
        if self.bulk_worker is not None:
            self.bulk_worker.stop()
            self.status.setText('현재 작품 조회를 마치면 중단할게. 이미 조회한 내용은 미리보기로 확인할 수 있어.')
            return
        if self.worker is not None:
            return
        entries = [(g.id, g.name, self.library.product_code(g)) for g in self.games
                   if is_code_only_title(g.name) and self.library.product_code(g)
                   and (self.library.meta(g).get('title') or '').strip() in ('', g.name)
                   and not (self.library.meta(g).get('localized_titles') or {}).get(
                       self.language_menu.currentData() or 'ko')]
        if not entries:
            QMessageBox.information(self, '조회 대상 없음', '선택 언어의 제목이 없는 품번 전용 게임이 없습니다.')
            return
        language = self.language_menu.currentData() or 'ko'
        if QMessageBox.question(self, '품번 일괄 조회',
                f'품번만 있는 {len(entries)}개 게임의 {LANGUAGES[language][0]} 제목을 공개 자료에서 조회할까요?\n'
                '여러 번의 인터넷 요청이 발생할 수 있습니다. 저장은 결과 확인 후에만 진행합니다.') != QMessageBox.StandardButton.Yes:
            return
        self.bulk_btn.setEnabled(False)
        self.bulk_worker = BulkTitleWorker(entries, language,
                                            self.library.store / 'localized_product_titles.json')
        self.bulk_worker.progress.connect(self.bulk_progress)
        self.bulk_worker.complete.connect(self.bulk_complete)
        self.bulk_worker.finished.connect(self.bulk_finished)
        self.status.setText(f'{len(entries)}개 작품의 공개 제목을 확인하는 중...')
        self.bulk_worker.start()
        self.set_enabled(self.current_game() is not None)


    def bulk_progress(self, finished: int, total: int, code: str):
        self.status.setText(f'품번 조회 {finished}/{total} · {code}')


    def bulk_complete(self, rows):
        if not rows:
            self.status.setText('품번 일괄 조회가 취소되었거나 결과가 없습니다.')
            return
        language = self.language_menu.currentData() or 'ko'
        dialog = BulkPreviewDialog(rows, language, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.status.setText('적용 취소 · 게임 이름을 변경하지 않았습니다.')
            return
        changed = 0
        for record in dialog.selected_rows():
            game = next((g for g in self.games if g.id == record['game_id']), None)
            if game is None or self.library.product_code(game) != record['code']:
                continue
            meta = self.library.meta(game)
            variants = dict(meta.get('localized_titles') or {})
            sources = dict(meta.get('localized_sources') or {})
            actual = record['language']
            variants[actual] = record['title']
            sources[actual] = record['source']
            self.library.update_meta(game, localized_titles=variants, localized_sources=sources)
            changed += 1
        self.refresh()
        self.status.setText(f'선택한 {changed}개 제목을 저장했어. 원본 게임 파일은 변경하지 않았어.')


    def bulk_finished(self):
        self.bulk_worker = None
        self.set_enabled(self.current_game() is not None)


    def closeEvent(self, event):
        # Destroying a running QThread can terminate the process abruptly.
        # The user's data is never auto-saved while the worker is active.
        if self.bulk_worker is not None and self.bulk_worker.isRunning():
            self.bulk_worker.stop()
            self.status.setText('조회 작업을 종료하는 중이야. 완료 후 창을 다시 닫아 줘.')
            event.ignore()
            return
        if self.worker is not None and self.worker.isRunning():
            self.status.setText('현재 조회가 완료된 다음 창을 닫아 줘.')
            event.ignore()
            return
        super().closeEvent(event)


    def save_code(self):
        game = self.current_game()
        if game is None or self.worker is not None:
            return
        try:
            code = normalize_code(self.code_input.text())
            self.library.set_product_code(game, code)
        except ValueError as exc:
            QMessageBox.warning(self, '품번 오류', str(exc))
            return
        self.refresh()
        self.status.setText(('작품 코드 ' + code + ' 저장 완료. 제목에 빠졌다면 자동으로 표시돼.'
                             if code else '품번 없음 저장 완료. 제목에 코드를 붙이지 않아.'))


    def save_title(self):
        game = self.current_game()
        if game is None or self.worker is not None:
            return
        candidate = self.edit.text().strip()
        if not candidate or len(candidate) > 240:
            QMessageBox.warning(self, '이름 확인', '이름은 1~240자로 입력하세요.')
            return
        try:
            code = normalize_code(self.code_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, '품번 오류', str(exc))
            return
        before = self.library.base_title(game)
        if candidate == before and code == self.library.product_code(game):
            self.status.setText('변경된 내용이 없습니다.')
            return
        try:
            save_display_title(self.library, game, candidate, source=self.suggestion_source)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '이름 저장 실패', str(exc))
            return
        self.library.update_meta(game, title_product_code=self.suggestion_code,
                                 product_code=code)
        self.refresh()
        self.status.setText('저장 완료! 제목과 별도 품번은 PlayDock 본체에서 새로고침하면 반영됩니다.')


    def reset_title(self):
        game = self.current_game()
        if not game or self.worker is not None:
            return
        self.edit.setText(game.name)
        self.suggestion_source = '원본 파일명'
        self.suggestion_code = ''
        self.source.setText('원래 파일명으로 표시 이름만 복원합니다. 저장 버튼을 눌러 확정하세요.')

