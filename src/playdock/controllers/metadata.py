"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from PySide6.QtWidgets import QDialog

from artwork import discover_local
from ui.artwork_dialog import OnlineArtworkDialog
from title_editor import TitleEditor
from ui.dialogs.title import BulkTitleSettingsDialog
from services.work_lookup_worker import WorkLookupThread
from ui.work_info_dialog import WorkPreviewDialog
from services.official_work_service import official_metadata_for_game
from services.identity_artwork_worker import IdentityArtworkThread
from services.official_artwork_service import apply_checked_images
from ui.dialogs.identity_artwork import IdentityArtworkDialog


from ui.dialogs.common import ask_yes_no, show_message


class MetadataControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def open_saved_official_page(self):
        """Open only a verified official store page from PlayDock's local DB."""
        game = self.current()
        if game is None:
            return
        try:
            record = official_metadata_for_game(self.library, game, self.work_db)
        except (OSError, ValueError):
            record = None
        if not record:
            show_message(self, '공식 작품정보 없음',
                         '해당 게임의 품번 / Steam App ID와 일치하는 저장된 정보가 없습니다.\n'
                         '정체 판독기를 실행했다면 PlayDock에서 새로고침을 눌러주세요.')
            return
        webbrowser.open(record['page_url'])

    def lookup_work_database(self):
        """Retrieve one user-selected work; no automatic site crawling."""
        game = self.current()
        if game is None:
            return
        code = self.library.product_code(game)
        if not code:
            show_message(self, '작품 코드가 없습니다',
                         '이 게임은 작품 코드가 없습니다. 게임 이름 관리자에서 RJ/VJ/BJ/EJ 코드를 등록하거나\n'
                         '기존 무료 이미지 검색 기능으로 작품을 찾아주세요.')
            return
        if self.work_lookup_worker is not None and self.work_lookup_worker.isRunning():
            show_message(self, '조회 중', '다른 작품의 정보를 조회하고 있습니다.')
            return
        cached = self.work_db.get_work(code)
        if cached and not ask_yes_no(self, '작품 DB',
                f'{code} 정보가 로컬 DB에 저장돼 있습니다.\n새로 DLsite에서 조회할까요?\n'
                '인터넷이 필요 없으면 [저장된 정보 보기]를 선택하세요.',
                'DLsite 새로 조회', '저장된 정보 보기'):
            self.preview_work_database(cached, game.id, is_cached=True)
            return
        worker = WorkLookupThread(code, self)
        self.work_lookup_worker = worker
        worker.complete.connect(lambda result, game_id=game.id:
                                self.preview_work_database(result, game_id, is_cached=False))
        worker.failed.connect(lambda error: show_message(self, '작품 정보 조회 실패', error))
        worker.finished.connect(self.work_lookup_finished)
        self.set_message(f'DLsite 작품 정보 조회 중: {code}')
        worker.start()


    def work_lookup_finished(self):
        self.work_lookup_worker = None
        self.set_message('')


    def preview_work_database(self, result, game_id, *, is_cached=False):
        game = next((g for g in self.games if g.id == game_id), None)
        if game is None:
            return
        dialog = WorkPreviewDialog(result, is_cached=is_cached, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if not is_cached:
                self.work_db.save_work(result)
            if dialog.apply_title.isChecked():
                from product_titles import display_title
                title = dialog.selected_title()
                if not title:
                    raise ValueError('적용 가능한 작품명이 없습니다.')
                self.library.update_meta(game, title=display_title(title, game.name, result['code']),
                                         prefer_manual_title=True)
            self.reload(prefer_id=game.id)
            self.set_message(f'작품 정보 확인 완료: {result["code"]} · DB 저장')
        except (OSError, ValueError) as exc:
            show_message(self, '작품 DB 저장 실패', str(exc))



    def identify_selected_game(self):
        """Run the same DLsite->Steam identity engine as the standalone scanner.

        Only the original archive basename and explicitly saved codes are read.
        Never inspect or rename ZIP/7z/RAR contents and never block the GUI.
        """
        game = self.current()
        if game is None:
            return
        if (self.identity_lookup_worker is not None
                and self.identity_lookup_worker.isRunning()):
            show_message(self, "정체 판독 중", "다른 게임의 정체 판독이 진행 중입니다.")
            return
        metadata = self.library.meta(game)
        label = game.archive.name if game.archive else game.name
        # The UI's manual code is additional evidence, not a new web search
        # against a private absolute archive path.
        code = self.library.product_code(game)
        if code and code.upper() not in label.upper():
            label += f" [{code}]"
        appid = str(metadata.get("steam_app_id") or "").strip()
        if appid and f"Steam {appid}" not in label:
            label += f" [Steam {appid}]"
        origin = "archive" if game.archive else "manual"
        worker = IdentityArtworkThread(label, origin=origin, parent=self)
        self.identity_lookup_worker = worker
        worker.complete.connect(
            lambda report, work, images, game_id=game.id:
            self._show_identity_artwork_result(game_id, report, work, images)
        )
        worker.failed.connect(
            lambda error: show_message(self, "정체 판독 실패", error))
        worker.finished.connect(self.identity_lookup_finished)
        self.set_message("DLsite → Steam 공식 품번 확인 및 이미지 조회 중…")
        worker.start()

    def identity_lookup_finished(self):
        worker = self.identity_lookup_worker
        self.identity_lookup_worker = None
        if worker is not None:
            worker.deleteLater()

    def _show_identity_artwork_result(self, game_id, report, work, images):
        game = next((g for g in self.games if g.id == game_id), None)
        if game is None:
            return
        if work is None:
            reasons = "\n".join(report.warnings[:3])
            if any(row.status == "verified" for row in report.works):
                reasons = "서로 다른 품번이 여럿 확인되어 자동 연결하지 않았습니다.\n" + reasons
            show_message(self, "정체 판독 결과", reasons or
                         "확인된 공식 작품이 없습니다. 품번을 확인해 주세요.")
            return
        folder = self.library.art_dir(game)
        existing = {kind for kind in ("hero", "icon")
                    if (folder / f"{kind}.png").is_file()}
        dialog = IdentityArtworkDialog(
            work, images, existing_kinds=existing, warnings=report.warnings,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_kinds()
        overwrites = selected & existing
        if overwrites:
            names = ", ".join("배너" if item == "hero" else "아이콘"
                              for item in sorted(overwrites))
            if not ask_yes_no(
                self, "기존 이미지 교체 확인",
                f"기존 {names} 이미지를 공식 이미지로 교체할까요?\n"
                "원본 이미지는 data/backups/artwork에 보관됩니다.\n"
                "취소하면 기존 이미지는 그대로 유지하고 공식 작품정보만 DB에 저장합니다.",
                "이미지 교체", "기존 이미지 유지",
            ):
                selected = set()
        try:
            saved = self.work_db.save_verified_results([report])
            if saved < 1:
                raise ValueError("공식 작품정보를 검증해 저장하지 못했습니다.")
            self.work_db.save_official_image_urls(
                work.store, work.code,
                {kind: offer.url for kind, offer in images.items()}
            )
            # A manual empty code means deliberately unlinked; do not undo it.
            metadata = self.library.meta(game)
            if "product_code" not in metadata or metadata.get("product_code"):
                self.library.update_meta(
                    game, artwork_identity_store=work.store,
                    artwork_identity_code=work.code,
                )
            applied = apply_checked_images(self.library, game, work, images, selected)
            self.reload(prefer_id=game_id)
            summary = ", ".join("배너" if kind == "hero" else "아이콘"
                                for kind in applied) if applied else "이미지 변경 없음"
            self.set_message(f"정체 판독 완료 · {work.store.upper()} {work.code} · {summary}")
        except (OSError, ValueError, RuntimeError) as exc:
            show_message(self, "작품정보·이미지 적용 실패", str(exc))

    def open_title_editor(self):
        """Open the selected game's editor inside PlayDock.exe."""
        game = self.current()
        if game is None:
            show_message(self, '게임을 선택하세요', '이름을 수정할 게임을 선택해 주세요.')
            return
        current = self.title_editor_window
        if current is not None and current.isVisible():
            current.raise_()
            current.activateWindow()
            return
        editor = TitleEditor(game.id, library=self.library, single_game_only=True)
        editor.closed.connect(self.title_editor_closed)
        self.title_editor_window = editor
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def title_editor_closed(self):
        """Refresh the visible title and preserve the selected game."""
        self.title_editor_window = None
        self.reload(prefer_id=self.selected_id)

    def open_bulk_name_settings(self):
        """User selects game checkboxes, previews, and confirms each bulk edit."""
        if self.title_editor_window is not None and self.title_editor_window.isVisible():
            show_message(self, '이름 설정 진행 중',
                         '현재 게임 이름 설정 창을 닫은 뒤 일괄 설정을 열어 주세요.')
            return
        if not self.games:
            show_message(self, '대상 없음', '이름을 설정할 게임이 없습니다.')
            return
        # All checkboxes start unchecked: selection is always explicit.
        dialog = BulkTitleSettingsDialog(self.library, self.games, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload(prefer_id=self.selected_id)
            self.set_message('선택한 게임들의 이름을 변경했습니다. 원본 압축파일은 그대로입니다.')


    def open_online_artwork(self):
        game = self.current()
        if game is None:
            return
        def confirm_replace(kind: str) -> bool:
            label = '배너' if kind == 'hero' else '아이콘'
            return ask_yes_no(self, '기존 이미지 교체',
                              f'이미 저장된 {label} 이미지가 있어.\n교체하면 이전 이미지는 data/backups/artwork에 백업돼.\n진행할까?',
                              '교체', '취소')
        dialog = OnlineArtworkDialog(self.library, game, self, confirm_replace=confirm_replace)
        dialog.applied.connect(lambda _kind: self.reload(prefer_id=game.id))
        dialog.exec()


    def open_artwork_library(self):
        folder = self.library.store / 'artwork_library'
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(str(folder))
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


    def refresh_local_art(self):
        game = self.current()
        if not game:
            return
        found = discover_local(self.library, game)
        if found:
            self.reload(prefer_id=game.id)
            self.set_message('로컬 이미지 적용: ' + ', '.join(found))
        else:
            show_message(self, '이미지 검색', '새로 찾은 배너·아이콘이 없습니다.\n'
                         '게임 폴더 또는 data/artwork_library/게임명 폴더에 이미지를 넣어 주세요.\n'
                         '기존 이미지는 덮어쓰지 않습니다.')

