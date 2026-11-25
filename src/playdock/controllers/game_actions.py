"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog

from core import uninstall_target, executable_candidates, chosen_executable, archive_requires_password
from services.launch_approval import (
    needs_launch_confirmation,
    launch_approval_changes,
    executable_selection_changes,
)
from artwork import save_image
from services.launch_options import parse_game_arguments


from ui.dialogs.common import ask_text, ask_choice, ask_yes_no, show_message, ask_archive_password
from workers.game_tasks import InstallThread, UninstallThread


class GameActionControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def edit_launch_options(self):
        game = self.current()
        if game is None or not game.installed:
            show_message(self, '게임 실행 옵션', '먼저 설치된 게임을 선택해 주세요.')
            return
        current = str(self.library.meta(game).get('launch_args', ''))
        updated, ok = ask_text(self, '게임 실행 옵션', 'EXE에 전달할 인수 (명령어가 아닌 인수만)', current)
        if not ok:
            return
        try:
            parse_game_arguments(updated)
            self.library.update_meta(game, launch_args=updated)
            self.set_message('게임 실행 옵션이 저장되었습니다.')
        except ValueError as exc:
            show_message(self, '실행 옵션 오류', str(exc))


    def main_action(self):
        game = self.current()
        if game is None:
            return
        if game.installed:
            self.launch_game()
        else:
            self.install_game()


    def uninstall_game(self):
        game = self.current()
        if game is None or not game.installed or game.external:
            return
        if self.install_worker is not None or self.uninstall_worker is not None:
            show_message(self, "작업 진행 중", "다른 설치 또는 제거 작업이 끝난 뒤 시도하세요.")
            return
        try:
            target = uninstall_target(game, self.library.archive_root)
        except (OSError, ValueError) as exc:
            show_message(self, "설치 제거 불가", str(exc))
            return
        note = "원본 ZIP·7z·RAR 압축파일, 모음집, 이미지 캐시는 그대로 유지됩니다."
        if game.archive is None:
            note += "\n원본 압축파일이 없는 게임은 제거 후 라이브러리 목록에서도 사라집니다."
        message = (f"'{self.library.title(game)}'의 설치를 제거할까요?\n\n"
                   f"휴지통으로 이동할 폴더:\n{target}\n\n"
                   "폴더 안에 저장된 세이브 데이터도 함께 이동할 수 있습니다.\n"
                   f"{note}\n\n"
                   "실행 중인 게임은 종료하고 진행하세요.")
        if not ask_yes_no(self, "게임 설치 제거", message, "휴지통으로 이동", "취소"):
            return
        self.removing_game = game
        self.uninstall_worker = UninstallThread(game, self.library.archive_root)
        self.uninstall_worker.complete.connect(self.uninstall_completed)
        self.uninstall_worker.failed.connect(self.uninstall_failed)
        self.uninstall_worker.finished.connect(self.uninstall_finished)
        self.main_button.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.set_message(f"설치 제거 중: {self.library.title(game)}")
        self.uninstall_worker.start()


    def uninstall_completed(self, target: str):
        game = self.removing_game
        # A new archive revision can contain different code at the same EXE
        # path, so require first-run approval again after a reinstall.
        if game is not None:
            try:
                self.library.update_meta(game, launch_confirmed_executable=None, executable=None)
            except OSError:
                pass  # The game was removed; preserve successful trash operation.
        self.reload(prefer_id=game.id if game else None)
        self.set_message("설치 제거 완료 · 게임 폴더를 휴지통으로 이동했습니다.")


    def uninstall_failed(self, reason: str):
        show_message(self, "설치 제거 실패", reason)
        self.set_message(f"설치 제거 실패: {reason}")


    def uninstall_finished(self):
        self.uninstall_worker = None
        self.removing_game = None
        self.present_game()


    def install_game(self):
        game = self.current()
        if not game or game.installed or game.archive is None:
            return
        if self.install_worker is not None or self.uninstall_worker is not None:
            show_message(self, "작업 진행 중", "현재 설치 또는 제거 작업이 끝난 뒤 시도하세요.")
            return
        if not ask_yes_no(self, "게임 설치", f"아래 압축파일을 해제하여 게임 폴더를 생성합니다.\n\n{game.archive.name}\n\n설치 위치: {game.root}\n원본 압축파일은 삭제하지 않습니다.\n\n계속할까요?", 'Yes', 'No'):
            return
        try:
            needs_password = archive_requires_password(game.archive)
        except Exception as exc:
            show_message(self, '압축파일 확인 실패', str(exc))
            return
        password = None
        if needs_password:
            password, accepted = ask_archive_password(self, game.archive.name)
            if not accepted:
                return
            if not password:
                show_message(self, '비밀번호 필요', '비밀번호를 입력해야 설치할 수 있습니다.')
                return
        self.install_worker = InstallThread(game, password=password)
        self.install_worker.progress.connect(self.progress.setValue)
        self.install_worker.complete.connect(self.install_completed)
        self.install_worker.failed.connect(self.install_failed)
        self.install_worker.finished.connect(self.install_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.main_button.setDisabled(True)
        self.set_message(f"설치 중: {game.name}")
        self.install_worker.start()


    def install_completed(self, folder: str):
        self.set_message(f"설치 완료: {folder}")
        show_message(self, "설치 완료", f"압축 해제가 완료되었습니다.\n{folder}")
        self.reload()


    def install_failed(self, reason: str):
        show_message(self, "설치 실패", reason)
        self.set_message(f"설치 실패: {reason}")


    def install_finished(self):
        self.progress.hide()
        self.install_worker = None
        self.present_game()


    def launch_game(self):
        game = self.current()
        if not game or not game.folder:
            return
        candidates = executable_candidates(game.folder, self.library.title(game))
        selected = self.library.meta(game).get("executable")
        if len(candidates) > 1 and not selected:
            self.pick_exe()
            if not self.library.meta(game).get("executable"):
                return
            # The dialog can change files or metadata; resolve again afterwards.
            exe = chosen_executable(self.library, game)
        else:
            exe = chosen_executable(self.library, game, candidates=candidates)
        if not exe:
            self.pick_exe()
            exe = chosen_executable(self.library, game)
        if not exe:
            show_message(self, "실행 불가", "실행 파일(.exe)을 찾지 못했습니다. 수동으로 선택하세요.")
            return
        try:
            first_run = needs_launch_confirmation(self.library.meta(game), game.folder, exe)
        except (OSError, ValueError) as exc:
            show_message(self, "실행 파일 오류", str(exc))
            return
        if first_run:
            # First approval is bound to this *game's* selected EXE. Later
            # launches of the same path don't interrupt the player.
            if not ask_yes_no(self, "첫 실행 확인",
                    f"이 게임에서 처음 실행할 파일입니다.\n\n{exe}\n\n"
                    "신뢰할 수 있는 파일인지 확인하세요. 승인 후에는 매번 묻지 않습니다.",
                    '실행', '취소'):
                return
        try:
            arguments = parse_game_arguments(str(self.library.meta(game).get('launch_args', '')))
        except ValueError as exc:
            show_message(self, '실행 옵션 오류', str(exc))
            return
        from PySide6.QtCore import QProcess
        started, pid = QProcess.startDetached(str(exe), arguments, str(exe.parent))
        if started:
            changes = {"last_started": __import__("datetime").datetime.now().isoformat(timespec="seconds")}
            if first_run:
                changes.update(launch_approval_changes(game.folder, exe))
            self.library.update_meta(game, **changes)
            self.set_message(f"게임 실행됨: {exe.name} (PID {pid})")
        else:
            show_message(self, "실행 실패", f"실행할 수 없습니다: {exe}")


    def pick_exe(self):
        game = self.current()
        if not game or not game.folder:
            return
        candidates = executable_candidates(game.folder, self.library.title(game))
        values = [str(p.relative_to(game.folder)) for p in candidates]
        values.append("[다른 EXE 찾아보기]")
        selected, ok = ask_choice(self, "실행파일 선택", "게임 실행 파일을 선택하세요:", values, 0)
        if not ok:
            return
        if selected == "[다른 EXE 찾아보기]":
            chosen, _ = QFileDialog.getOpenFileName(
                self, "게임 EXE 선택", str(game.folder), "실행 파일 (*.exe)",
                options=QFileDialog.Option.DontUseNativeDialog)
            if not chosen:
                return
            path = Path(chosen).resolve()
            if not path.is_relative_to(game.folder.resolve()):
                show_message(self, "선택 오류", "게임 설치 폴더 내부의 실행파일만 지정할 수 있습니다.")
                return
            selected = str(path.relative_to(game.folder))
        try:
            changes = executable_selection_changes(game.folder, selected, self.library.meta(game))
        except (OSError, ValueError) as exc:
            show_message(self, "실행 파일 오류", str(exc))
            return
        self.library.update_meta(game, **changes)
        self.present_game()


    def open_game_folder(self):
        game = self.current()
        if not game:
            return
        path = game.folder or (game.archive.parent if game.archive else game.root)
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


    def change_image(self, kind: str):
        game = self.current()
        if not game:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 선택", str(game.root),
            "이미지 (*.png *.jpg *.jpeg *.webp *.bmp)",
            options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            save_image(Path(path), self.library.art_dir(game) / f"{kind}.png", kind)
            self.library.update_meta(game, artwork_source="사용자가 지정한 이미지")
            self.reload(prefer_id=game.id)
        except Exception as exc:
            show_message(self, "이미지 변경 실패", str(exc))

