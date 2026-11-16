"""사용자 요청 시 DLsite 단일 작품을 조회하는 백그라운드 작업자."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from work_db import fetch_dlsite_work


class WorkLookupThread(QThread):
    complete = Signal(object)
    failed = Signal(str)

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self.code = code

    def run(self):
        try:
            self.complete.emit(fetch_dlsite_work(self.code))
        except Exception as exc:
            self.failed.emit(str(exc))


