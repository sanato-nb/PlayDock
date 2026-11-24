"""Bulk artwork uses a single worker, keeping only one game's images in memory."""
from PySide6.QtCore import QThread, Signal
from services.bulk_official_artwork import apply_bulk_artwork


class BulkOfficialArtworkThread(QThread):
    progress = Signal(int, int, str)

    def __init__(self, library, db_path, jobs, parent=None):
        super().__init__(parent)
        self.library, self.db_path, self.jobs = library, db_path, tuple(jobs)
        self.results = []

    def run(self):
        try:
            self.results = apply_bulk_artwork(
                self.library, self.db_path, self.jobs,
                cancelled=self.isInterruptionRequested, progress=self.progress.emit)
        except Exception as exc:
            self.results = [{"name": "작업 오류", "applied": [],
                             "skipped": [type(exc).__name__]}]
