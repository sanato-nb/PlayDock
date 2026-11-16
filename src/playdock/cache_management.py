"""Image cache inventory and conservative cleanup for PlayDock.

Only known artwork filenames in hashed game-cache folders can be moved to the
recycle bin. Never remove meta.json, collections, executable selection,
configuration, or an installed game's files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterable

IMAGE_FILES = ("hero.png", "icon.png")
GAME_ID = re.compile(r"^[0-9a-f]{22}$")


@dataclass(frozen=True)
class CacheStats:
    files: int = 0
    bytes: int = 0


def _safe_folder(root: Path, game_id: str) -> Path | None:
    if not GAME_ID.fullmatch(game_id):
        return None
    folder = root / game_id
    if folder.is_symlink() or not folder.is_dir():
        return None
    return folder


def image_files(cache_root: Path, game_ids: Iterable[str] | None = None) -> list[Path]:
    """List only normal image files within directly nested, valid cache IDs.

    Does not create directories, traverse symlinks, or inspect external paths.
    """
    cache_root = Path(cache_root)
    if not cache_root.is_dir() or cache_root.is_symlink():
        return []
    if game_ids is None:
        ids = [p.name for p in cache_root.iterdir() if p.is_dir() and not p.is_symlink()]
    else:
        ids = list(game_ids)
    files = []
    for game_id in sorted(set(ids)):
        folder = _safe_folder(cache_root, game_id)
        if folder is None:
            continue
        for filename in IMAGE_FILES:
            path = folder / filename
            if path.is_file() and not path.is_symlink():
                files.append(path)
    return files


def image_stats(cache_root: Path, game_ids: Iterable[str] | None = None) -> CacheStats:
    files = image_files(cache_root, game_ids)
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return CacheStats(len(files), total)


def recycle_images(cache_root: Path, game_ids: Iterable[str] | None = None,
                   recycle: Callable[[str], object] | None = None) -> CacheStats:
    """Move cached artwork to OS trash without touching game metadata.

    Errors are deliberately surfaced, never silently replaced with permanent
    deletion. The caller must show a confirmation dialog before invoking.
    """
    if recycle is None:
        try:
            from send2trash import send2trash as recycle
        except ImportError as exc:
            raise RuntimeError("휴지통 이동을 위해 send2trash가 필요합니다.") from exc
    files = image_files(cache_root, game_ids)
    moved, total = 0, 0
    for path in files:
        size = path.stat().st_size
        recycle(str(path))
        moved += 1
        total += size
    return CacheStats(moved, total)
