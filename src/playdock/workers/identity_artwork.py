"""Selected-game identity scanner + official artwork, on a background QThread.

Uses exactly the standalone DLsite->Steam code-only verification engine.
No archive extraction or filename renaming, no GPT/image generation.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from pathlib import Path

from database.work_repository import WorkDatabase
from integrations.official_lookup.code_only import (
    InputItem, Work, Result, check, codes_in, steam_ids_in,
)
from services.official_artwork_service import trusted_image_url
from services.official_artwork_service import prepare_official_images


class IdentityArtworkThread(QThread):
    complete = Signal(object, object, object)  # scanner Result, verified Work|None, images
    failed = Signal(str)

    def __init__(self, label: str, *, origin: str = "archive", db_path=None,
                 verified_work=None, parent=None):
        super().__init__(parent)
        self.label = label
        self.origin = origin
        self.db_path = Path(db_path) if db_path is not None else None
        self.verified_work = verified_work

    def run(self):
        try:
            cache = {}
            store_records = {}
            if self.db_path is not None and self.db_path.is_file():
                db = WorkDatabase(self.db_path.parent, db_path=self.db_path)
                for store, codes in (("dlsite", codes_in(self.label)),
                                     ("steam", steam_ids_in(self.label))):
                    for code in codes:
                        record = db.get_official_work(store, code)
                        if record:
                            key = code if store == "dlsite" else "STEAM:" + code
                            cache[key] = Work(code, record["title"],
                                               record.get("category") or "",
                                               record["page_url"], "verified", store)
                            store_records[(store, code)] = record
            # The local archive basename may no longer contain a store code.
            # Official image mode has a verified DB link; read that exact row,
            # never reconstruct its identity from the filename.
            if (self.verified_work is not None and self.db_path is not None
                    and self.db_path.is_file()):
                work = self.verified_work
                verified = db.get_official_work(work.store, work.code)
                if verified is not None:
                    store_records[(work.store, work.code)] = verified
            item = InputItem(self.label, self.origin)
            if self.verified_work is not None:
                work = self.verified_work
                # Image mode never calls the network identity checker.
                if (work.store, work.code) not in store_records:
                    raise ValueError("공식 작품정보가 PlayDock DB에 없습니다.")
                result = Result(self.label, self.origin, "confirmed",
                                (work,), selected_store=work.store)
            else:
                # Standalone identity scanner remains available for development.
                result = check(item, cache=cache) if cache else check(item)
                verified = [row for row in result.works
                            if row.status == "verified" and
                            row.store == result.selected_store]
                if len(verified) != 1:
                    self.complete.emit(result, None, {})
                    return
                work = verified[0]
            try:
                saved = store_records.get((work.store, work.code))
                candidates = {}
                if saved:
                    candidates = {
                        row["kind"]: row["url"]
                        for row in saved.get("images", [])
                        if isinstance(row, dict)
                        and row.get("kind") in ("hero", "icon")
                        and trusted_image_url(work.store, work.code, row.get("url", ""))
                    }
                if candidates:
                    artwork = prepare_official_images(work, candidates=candidates)
                else:
                    artwork = prepare_official_images(work)
            except Exception:
                # Successful identity lookup must not fail because an image CDN is down.
                artwork = {}
            self.complete.emit(result, work, artwork)
        except Exception as exc:
            self.failed.emit(f"게임 정체 판독을 완료하지 못했습니다: {type(exc).__name__}")
