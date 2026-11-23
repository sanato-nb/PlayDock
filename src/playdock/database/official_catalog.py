"""Shared site/code validation and PlayDock installation-relative DB location.

The independent scanner does NOT create an official_works.sqlite3 file. It
writes to the same installed PlayDock/data/playdock.db as the main app.
A one-time remembered install-folder path is only a pointer, not a second DB.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

DL_CODE = re.compile(r"(?:RJ|VJ|BJ|EJ)\d{6,8}\Z", re.I)
STEAM_ID = re.compile(r"[1-9]\d{2,9}\Z")
_CONFIG_FILE = "scanner_install_folder.json"


def _profile_root() -> Path:
    if os.name == "nt":
        path = os.environ.get("LOCALAPPDATA")
        return (Path(path) if path else (Path.home() / "AppData" / "Local")) / "PlayDock"
    return Path(os.environ.get("XDG_DATA_HOME") or
                (Path.home() / ".local" / "share")) / "PlayDock"


def legacy_catalog_path() -> Path:
    """Historical scanner DB path; migration input only, never new output."""
    return Path(os.environ.get("PLAYDOCK_OFFICIAL_CATALOG_PATH") or
                (_profile_root() / "official_works.sqlite3")).expanduser()


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


def installed_database_path(folder: str | Path) -> Path | None:
    """Recognize only a genuine PlayDock installation with an installer marker."""
    root = Path(folder).expanduser()
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        return None
    # Imported lazily so the scanner can use this module without Qt.
    from local_storage import marker_is_valid
    if not marker_is_valid(root):
        return None
    data_dir = root / "data"
    if data_dir.is_symlink() or data_dir.is_junction():
        return None
    return data_dir / "playdock.db"


def default_catalog_path() -> Path | None:
    """Find B-location DB without creating an unrelated user-profile DB."""
    direct = os.environ.get("PLAYDOCK_DB_PATH")
    if direct:
        return Path(direct).expanduser()
    install = os.environ.get("PLAYDOCK_INSTALL_DIR")
    if install:
        path = installed_database_path(install)
        if path:
            return path
    if getattr(sys, "frozen", False):
        nearby = installed_database_path(Path(sys.executable).resolve().parent)
        if nearby:
            return nearby
    remembered = _profile_root() / _CONFIG_FILE
    if remembered.is_file() and not remembered.is_symlink():
        try:
            saved = json.loads(remembered.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                return installed_database_path(saved.get("install_folder", ""))
        except (OSError, ValueError, TypeError):
            return None
    return None


def remember_install_folder(folder: str | Path) -> Path:
    """Record a verified PlayDock install folder, never store a second SQLite DB."""
    db = installed_database_path(folder)
    if db is None:
        raise ValueError("PlayDock 설치 표식을 찾을 수 없습니다. PlayDock 설치 폴더를 선택해 주세요.")
    target = _profile_root() / _CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"install_folder": str(Path(folder).resolve())},
                      ensure_ascii=False, indent=2)
    fd, staging = tempfile.mkstemp(prefix=".pd-scanner-", suffix=".tmp",
                                   dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            writer.write(data)
        os.replace(staging, target)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    return db


class OfficialWorkCatalog:
    """Thin backward-compatible scanner adapter to the shared works table."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_catalog_path()

    def save_verified_results(self, results) -> int:
        # Never create a new works DB for a scan with no verified official row.
        if not any(w.status == "verified" and w.title and
                   _valid_identity(str(w.store).lower(), str(w.code).strip(),
                                   str(w.url).strip())
                   for row in results for w in row.works):
            return 0
        if self.path is None:
            raise FileNotFoundError("PlayDock 설치 폴더의 공용 DB 경로가 지정되지 않았습니다.")
        from database.work_repository import WorkDatabase
        return WorkDatabase(self.path.parent, db_path=self.path).save_verified_results(results)

    def get_work(self, store: str, product_id: str):
        if self.path is None or not self.path.is_file():
            return None
        from database.work_repository import WorkDatabase
        return WorkDatabase(self.path.parent, db_path=self.path).get_official_work(
            store, product_id)
