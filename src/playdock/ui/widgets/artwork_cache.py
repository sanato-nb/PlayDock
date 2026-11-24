"""GUI-thread pixmap loading with revision-aware, bounded Qt cache.

Original artwork is never modified. Only collection tiles use scaled pixmaps;
the selected-game banner remains full resolution. Qt owns cache eviction.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import stat

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader, QPixmap, QPixmapCache

TILE_MAX_EDGE = 768


def file_revision(path: Path):
    """Stat once; missing/non-file images are not cached."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return None
        return (str(path.absolute()), info.st_mtime_ns, info.st_size,
                info.st_ctime_ns, info.st_ino, info.st_dev)
    except OSError:
        return None


def cached_pixmap(revision, variant, loader):
    key = "PlayDock-art-v1:" + sha256(repr((revision, variant)).encode("utf-8")).hexdigest()
    pix = QPixmapCache.find(key)
    if pix is not None and not pix.isNull():
        return pix
    pix = loader()
    if not pix.isNull():
        QPixmapCache.insert(key, pix)
    return pix


def _read_pixmap(path: Path, max_edge: int | None):
    reader = QImageReader(str(path))
    if max_edge is not None:
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > max_edge:
            factor = max_edge / max(size.width(), size.height())
            reader.setScaledSize(QSize(max(1, round(size.width() * factor)),
                                       max(1, round(size.height() * factor))))
    image = reader.read()
    if image.isNull():
        return QPixmap()
    return QPixmap.fromImage(image)


def artwork_pixmap(path: Path | None, *, max_edge: int | None = None):
    if path is None:
        return QPixmap()
    revision = file_revision(path)
    if revision is None:
        return QPixmap()
    return cached_pixmap(revision, ("artwork", max_edge),
                         lambda: _read_pixmap(path, max_edge))
