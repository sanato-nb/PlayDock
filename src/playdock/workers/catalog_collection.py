"""Qt adapter for background, cancelable PlayDock unified DB collection."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QThread, Signal

from services.catalog_collection_service import collect_batch
from services.identity_import_service import collect_import_batch


class CatalogCollectionThread(QThread):
    progress = Signal(int, int, object)   # completed, total, CatalogEvent
    complete = Signal(object, bool)       # list[CatalogEvent], was_cancelled
    failed = Signal(str)

    def __init__(self, entries, db_path: Path, parent=None, *, import_library=None):
        super().__init__(parent)
        self.entries = tuple(entries)
        self.db_path = Path(db_path)
        self.import_library = import_library

    def run(self):
        try:
            options = dict(is_cancelled=self.isInterruptionRequested,
                           callback=lambda i, total, event: self.progress.emit(i, total, event))
            if self.import_library is None:
                events = collect_batch(self.entries, self.db_path, **options)
            else:
                events = collect_import_batch(self.entries, self.import_library,
                                              self.db_path, **options)
            self.complete.emit(events, len(events) < len(self.entries))
        except Exception as exc:
            # Keep the PlayDock window alive on unexpected SQLite failures.
            self.failed.emit(f"공식정보 수집 오류: {type(exc).__name__}")
