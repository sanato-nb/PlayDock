"""Stable game identity and safe folder/name helpers (no UI or file mutation)."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re


def game_key(name: str) -> str:
    """Pair an archive and a top-level folder with the same name (case-insensitive)."""
    return re.sub(r"\s+", " ", name.strip()).casefold()

def safe_folder_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name or name.casefold() in {"con", "prn", "aux", "nul"}:
        name = "game_" + sha256(name.encode()).hexdigest()[:8]
    return name[:130]

@dataclass
class Game:
    key: str
    name: str
    root: Path
    archive: Path | None = None
    folder: Path | None = None
    external: bool = False  # Manually linked game; never uninstall its folder.

    @property
    def id(self) -> str:
        if self.external:
            return sha256(('external|' + self.key).encode('utf-8')).hexdigest()[:22]
        return sha256((str(self.root.resolve()).casefold() + "|" + self.key).encode("utf-8")).hexdigest()[:22]

    @property
    def installed(self) -> bool:
        return self.folder is not None and self.folder.is_dir()

    @property
    def status(self) -> str:
        if self.installed:
            return "설치됨"
        if self.archive:
            return "설치 가능"
        return "경로 없음"
