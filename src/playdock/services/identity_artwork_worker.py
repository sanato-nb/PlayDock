"""Selected-game identity scanner + official artwork, on a background QThread.

Uses exactly the standalone DLsite->Steam code-only verification engine.
No archive extraction or filename renaming, no GPT/image generation.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from experiments.dlsite_detector.code_only import InputItem, check
from services.official_artwork_service import prepare_official_images


class IdentityArtworkThread(QThread):
    complete = Signal(object, object, object)  # scanner Result, verified Work|None, images
    failed = Signal(str)

    def __init__(self, label: str, *, origin: str = "archive", parent=None):
        super().__init__(parent)
        self.label = label
        self.origin = origin

    def run(self):
        try:
            result = check(InputItem(self.label, self.origin))
            verified = [row for row in result.works
                        if row.status == "verified" and row.store == result.selected_store]
            if len(verified) != 1:
                # Ambiguous/missing verification must not auto-apply images.
                self.complete.emit(result, None, {})
                return
            work = verified[0]
            try:
                artwork = prepare_official_images(work)
            except Exception:
                # Successful identity lookup must not fail because an image CDN is down.
                artwork = {}
            self.complete.emit(result, work, artwork)
        except Exception as exc:
            self.failed.emit(f"게임 정체 판독을 완료하지 못했습니다: {type(exc).__name__}")
