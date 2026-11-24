"""PlayDock controller for batch official game-information DB collection."""
from __future__ import annotations

from services.catalog_collection_service import (
    game_catalog_entries, partition_catalog_entries, make_missing_code_prompt,
)
from services.catalog_collection_worker import CatalogCollectionThread
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

    def catalog_collection_finished(self):
        worker, self.catalog_worker = self.catalog_worker, None
        if worker is not None:
            worker.deleteLater()
        # Reflect new official title/category without disturbing the selection.
        if self.current() is not None:
            self.present_game()
        else:
            self.refresh_function_availability()
        if self.catalog_dialog is not None and self.catalog_dialog.running:
            self.catalog_dialog.on_failed("작업이 종료되었습니다.")
