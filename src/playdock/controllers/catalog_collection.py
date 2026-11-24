"""PlayDock controller for batch official game-information DB collection."""
from __future__ import annotations

from dataclasses import replace
from PySide6.QtWidgets import QDialog
from services.identity_import_service import prepare_identity_import, approve_verified_import
from ui.dialogs.identity_import import IdentityImportDialog, IdentityImportPreviewDialog

from services.catalog_collection_service import (
    game_catalog_entries, partition_catalog_entries, make_missing_code_prompt,
)
from workers.catalog_collection import CatalogCollectionThread
from ui.dialogs.catalog_collection import CatalogCollectionDialog
from ui.dialogs.common import ask_yes_no, show_message


class CatalogCollectionControllerMixin:
    def collect_library_information(self):
        """User-initiated batch: scan filenames, fill works DB, no game edits."""
        if self.catalog_worker is not None and self.catalog_worker.isRunning():
            dialog = self.catalog_dialog
            if dialog is not None:
                dialog.raise_()
                dialog.activateWindow()
            return
        if not self.games:
            show_message(self, "게임 정보 수집", "라이브러리에 등록된 게임이 없습니다.")
            return
        all_entries = game_catalog_entries(self.library, self.games)
        entries, no_code = partition_catalog_entries(all_entries)
        if not ask_yes_no(
            self, "게임 정보 수집",
            f"전체 {len(all_entries)}개 게임 중 품번·Steam App ID가 확인된 "
            f"{len(entries)}개만 공식 사이트에서 조회합니다.\n"
            f"품번 없는 압축게임 {len(no_code)}개는 사전 제외하고, 수집 완료 후 "
            "AI 조사용 프롬프트를 만들 수 있습니다.\n\n"
            "기존 DB 정보는 재사용하며, 게임 이름·압축파일·이미지는 변경하지 않습니다.",
            "수집 시작", "취소",
        ):
            return
        # Preserve the first-seen original archive filename for future
        # display-name restoration. Never rename the actual ZIP/7z/RAR.
        for game in self.games:
            if game.archive is not None:
                meta = self.library.meta(game)
                if "original_archive_name" not in meta:
                    self.library.update_meta(
                        game, original_archive_name=game.archive.name,
                    )
        dialog = CatalogCollectionDialog(
            len(entries),
            excluded_no_code=tuple(entry.label for entry in no_code),
            prompt_text=make_missing_code_prompt(no_code),
            parent=self,
        )
        self.catalog_dialog = dialog
        dialog.importRequested.connect(self.import_identity_results)
        if not entries:
            # No network calls needed; still offer the AI handoff after finish.
            dialog.on_complete([], interrupted=False)
            dialog.show()
            if self.current() is not None:
                self.present_game()
            return
        worker = CatalogCollectionThread(entries, self.work_db.path, parent=self)
        self.catalog_worker = worker
        dialog.cancelRequested.connect(worker.requestInterruption)
        worker.progress.connect(dialog.on_progress)
        worker.complete.connect(dialog.on_complete)
        worker.failed.connect(dialog.on_failed)
        worker.finished.connect(self.catalog_collection_finished)
        dialog.show()
        worker.start()

    def import_identity_results(self):
        previous = self.catalog_dialog
        if previous is None or previous.running or (self.catalog_worker is not None and self.catalog_worker.isRunning()):
            return
        editor = IdentityImportDialog(previous)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            proposals, rejected = prepare_identity_import(
                editor.edit.toPlainText(), self.library, self.games, self.work_db,
                allowed_names=previous.no_code)
        except (ValueError, OSError) as exc:
            show_message(previous,"AI 결과 가져오기 실패",str(exc))
            return
        preview = IdentityImportPreviewDialog(proposals, rejected, previous)
        if preview.exec() != QDialog.DialogCode.Accepted:
            return
        selected = preview.selected_proposals()
        chosen_ids = {p.game.id for p in selected}
        rejected = list(rejected) + [f"{p.filename}: 조회 미선택 · {p.reason or '근거 미제공'}"
                                    for p in proposals if p.game.id not in chosen_ids]
        proposals = selected
        if not proposals:
            return
        # Only selected candidates are checked; no game link until a second approval.
        dialog = CatalogCollectionDialog(len(proposals),parent=self)
        dialog.import_mode = True
        dialog.setWindowTitle("AI 품번 공식 조회 · PlayDock DB")
        dialog.import_reasons = list(rejected)
        dialog.importRequested.connect(self.import_identity_results)
        dialog.setModal(True)
        self.catalog_dialog = dialog
        previous.accept()
        worker = CatalogCollectionThread(proposals,self.work_db.path,parent=self,
                                         import_library=self.library)
        self.catalog_worker = worker
        dialog.cancelRequested.connect(worker.requestInterruption)
        worker.progress.connect(dialog.on_progress)
        # Keep the dialog locked until the final approval and summary are ready.
        worker.failed.connect(dialog.on_failed)
        worker.finished.connect(self.catalog_collection_finished)
        dialog.show()
        worker.start()

    def catalog_collection_finished(self):
        worker, self.catalog_worker = self.catalog_worker, None
        imported = worker is not None and getattr(worker,"import_library",None) is not None
        if worker is not None:
            worker.deleteLater()
        # Newly registered IDs affect display overlays and lists; reload once.
        if imported:
            dialog = self.catalog_dialog
            events = list(worker.import_events)
            interrupted = worker.import_interrupted or len(events) < len(worker.entries)
            import_error = worker.import_error
            if import_error:
                dialog.import_reasons.append(import_error)
            successful = {e.game_id for e in events if e.outcome in ("cached","fetched") and not e.connected}
            verified = []
            titles = {}
            for p in worker.entries:
                if p.game.id in successful:
                    record = self.work_db.get_official_work(p.store,p.code)
                    if record and record.get("title"):
                        titles[p.game.id] = record["title"]
                        verified.append(p)
            verified_ids = {p.game.id for p in verified}
            events_by_id = {e.game_id:e for e in events}
            lookup_failures = []
            for p in worker.entries:
                if p.game.id not in verified_ids:
                    event = events_by_id.get(p.game.id)
                    reason = (event.message if event and event.outcome not in ("cached","fetched")
                              else "공식 작품명 확인 불가" if event else "조회 미처리")
                    lookup_failures.append(f"{p.filename} — {reason}")
            if not interrupted and (verified or lookup_failures):
                preview = IdentityImportPreviewDialog(verified, lookup_failures, dialog, official_titles=titles)
                if preview.exec() == QDialog.DialogCode.Accepted:
                    approved = approve_verified_import(preview.selected_proposals(), events, self.library, self.work_db)
                    registered = {e.game_id:e for e in approved}
                    events = [registered.get(e.game_id,e) for e in events]
            events = [replace(e, message="사용자 미선택 또는 중단 · 품번 미등록")
                      if e.outcome in ("cached","fetched") and not e.connected else e
                      for e in events]
            self.reload(prefer_id=self.selected_id)
            _, missing = partition_catalog_entries(game_catalog_entries(self.library,self.games))
            dialog.set_remaining(missing, make_missing_code_prompt(missing), events)
            if import_error:
                dialog.on_failed(import_error)
            else:
                dialog.on_complete(events, interrupted=interrupted)
        elif self.current() is not None:
            self.present_game()
        else:
            self.refresh_function_availability()
        if self.catalog_dialog is not None and self.catalog_dialog.running:
            self.catalog_dialog.on_failed("작업이 종료되었습니다.")
