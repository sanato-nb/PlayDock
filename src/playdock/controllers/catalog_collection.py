"""PlayDock controller for batch official game-information DB collection."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog

from services.catalog_collection_service import game_catalog_entries
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
        entries = game_catalog_entries(self.library, self.games)
        if not ask_yes_no(
            self, "게임 정보 수집",
            f"현재 라이브러리 {len(entries)}개 게임의 품번을 확인해\n"
            "DLsite → Steam 공식정보를 playdock.db에 저장할까요?\n\n"
            "이미 저장된 작품은 재사용하며, 확인되지 않은 게임은 실패 목록에 표시합니다.\n"
            "게임 제목·압축파일·기존 배너·아이콘은 변경하지 않습니다.",
            "수집 시작", "취소",
        ):
            return
        dialog = CatalogCollectionDialog(len(entries), parent=self)
        worker = CatalogCollectionThread(entries, self.work_db.path, parent=self)
        self.catalog_dialog = dialog
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
        if self.catalog_dialog is not None and self.catalog_dialog.running:
            self.catalog_dialog.on_failed("작업이 종료되었습니다.")
