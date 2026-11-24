"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core import Game, install, uninstall_to_recycle_bin
from save_backups import create_save_backup, restore_save_backup


class InstallThread(QThread):
    progress = Signal(int)
    complete = Signal(str)
    failed = Signal(str)

    def __init__(self, game: Game, password: str | None = None):
        super().__init__()
        self.game = game
        self.password = password

    def run(self):
        try:
            folder = install(self.game, lambda n: self.progress.emit(n), password=self.password)
            self.complete.emit(str(folder))
        except Exception as e:
            self.failed.emit(str(e))


class UninstallThread(QThread):
    complete = Signal(str)
    failed = Signal(str)

    def __init__(self, game: Game, archive_root: Path):
        super().__init__()
        self.game = game
        self.archive_root = archive_root

    def run(self):
        try:
            target = uninstall_to_recycle_bin(self.game, self.archive_root)
            self.complete.emit(str(target))
        except Exception as exc:
            self.failed.emit(str(exc))


class SaveBackupThread(QThread):
    complete = Signal(str)
    failed = Signal(str)

    def __init__(self, operation: str, path: Path, destination: Path,
                 title: str = '', game_id: str = ''):
        super().__init__()
        self.operation, self.path, self.destination = operation, path, destination
        self.title, self.game_id = title, game_id

    def run(self):
        try:
            if self.operation == 'backup':
                result = create_save_backup(self.path, self.destination, self.title, self.game_id)
            elif self.operation == 'restore':
                result = restore_save_backup(self.path, self.destination)
            else:
                raise ValueError('알 수 없는 세이브 작업입니다.')
            self.complete.emit(str(result))
        except Exception as exc:
            self.failed.emit(str(exc))

