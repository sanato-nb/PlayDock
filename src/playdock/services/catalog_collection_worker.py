"""Qt adapter for background, cancelable PlayDock unified DB collection."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QThread, Signal

from services.catalog_collection_service import collect_batch


class CatalogCollectionThread(QThread):
    progress = Signal(int, int, object)   # completed, total, CatalogEvent
    complete = Signal(object, bool)       # list[CatalogEvent], was_cancelled
    failed = Signal(str)

    def __init__(self, entries, db_path: Path, parent=None):
        super().__init__(parent)
        self.entries = tuple(entries)
        self.db_path = Path(db_path)

    def run(self):
        try:
            events = collect_batch(
                self.entries, self.db_path,
                is_cancelled=self.isInterruptionRequested,
                callback=lambda i, total, event: self.progress.emit(i, total, event),
            )
            self.complete.emit(events, len(events) < len(self.entries))
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(f"공식정보 수집 오류: {type(exc).__name__}: {str(exc)[:180]}")
