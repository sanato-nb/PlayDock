"""Shared, per-user official work metadata catalog for PlayDock.

The independent filename scanner writes only verified public store facts.
Other PlayDock features can query the same SQLite file without importing the
scanner or touching user library/game records. No network requests here.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

DATABASE_FILENAME = "official_works.sqlite3"
DL_CODE = re.compile(r"(?:RJ|VJ|BJ|EJ)\d{6,8}\Z", re.I)
STEAM_ID = re.compile(r"[1-9]\d{2,9}\Z")


def default_catalog_path() -> Path:
    """Stable user-specific location; never in the scanned games folder."""
    override = os.environ.get("PLAYDOCK_OFFICIAL_CATALOG_PATH")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or
                    (Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or
                    (Path.home() / ".local" / "share"))
    return root / "PlayDock" / DATABASE_FILENAME


def _valid_identity(store: str, product_id: str, page_url: str) -> bool:
    if store == "dlsite":
        valid_id = DL_CODE.fullmatch(product_id) is not None
        host = "www.dlsite.com"
    elif store == "steam":
        valid_id = STEAM_ID.fullmatch(product_id) is not None
        host = "store.steampowered.com"
    else:
        return False
    try:
        parts = urlsplit(page_url)
    except ValueError:
        return False
    return bool(valid_id and parts.scheme == "https" and
                parts.hostname == host and not parts.username and
                not parts.password and product_id.casefold() in
                parts.path.casefold())


class OfficialWorkCatalog:
    """Read/write official facts using the composite (store, product_id) key."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_catalog_path()

    def save_verified_results(self, results) -> int:
        """Store confirmed works from any scan status, ignoring failed lookups.

        Duplicate IDs across multiple scanned filenames are written only once.
        Failed/unknown lookups cannot erase previously verified metadata.
        The database is not created when nothing was verified.
        """
        records: dict[tuple[str, str], tuple[str, ...]] = {}
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for result in results:
            for work in result.works:
                if work.status != "verified":
                    continue
                store = str(work.store).lower().strip()
                product_id = str(work.code).strip().upper() if store == "dlsite" else str(work.code).strip()
                title = str(work.title or "").strip()
                category = str(work.category or "").strip()
                url = str(work.url or "").strip()
                if (not title or len(title) > 1000 or len(category) > 240 or
                        len(url) > 2048 or
                        not _valid_identity(store, product_id, url)):
                    continue
                records[(store, product_id)] = (
                    store, product_id, title, category, url, checked_at)
        if not records:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=8)) as con:
            con.execute("PRAGMA busy_timeout=8000")
            with con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS official_works (
                        store TEXT NOT NULL CHECK(store IN ('dlsite','steam')),
                        product_id TEXT NOT NULL,
                        official_title TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT '',
                        page_url TEXT NOT NULL,
                        verified_at_utc TEXT NOT NULL,
                        PRIMARY KEY (store, product_id)
                    )
                """)
                con.executemany("""
                    INSERT INTO official_works
                    (store, product_id, official_title, category, page_url, verified_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(store, product_id) DO UPDATE SET
                        official_title=excluded.official_title,
                        category=excluded.category,
                        page_url=excluded.page_url,
                        verified_at_utc=excluded.verified_at_utc
                """, records.values())
        return len(records)

    def get_work(self, store: str, product_id: str) -> dict | None:
        """Read existing metadata without creating or modifying the DB."""
        store = str(store).lower().strip()
        product_id = str(product_id).strip().upper() if store == "dlsite" else str(product_id).strip()
        if (not self.path.is_file() or
                not _valid_identity(store, product_id,
                                    f"https://www.dlsite.com/a/{product_id}" if store == "dlsite"
                                    else f"https://store.steampowered.com/app/{product_id}/")):
            return None
        with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            try:
                row = con.execute(
                    """SELECT store, product_id, official_title, category, page_url, verified_at_utc
                       FROM official_works WHERE store=? AND product_id=?""",
                    (store, product_id)).fetchone()
            except sqlite3.OperationalError:
                return None
        return dict(row) if row else None
