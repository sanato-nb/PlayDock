"""Normalize small / padded icon images for a consistent library sidebar.

This module intentionally never edits the original game artwork cache. The
Pillow part is Qt-independent so it can be tested without a desktop session.
"""
from __future__ import annotations

from io import BytesIO
from functools import lru_cache
from pathlib import Path

from PIL import Image


NORMALIZED_SIZE = 96
IMAGE_FILL = 0.92


def normalized_icon_png(path: Path, output_size: int = NORMALIZED_SIZE) -> bytes:
    """Return a square PNG where visible content fills most of the icon.

    Transparent padding is cropped; opaque artwork isn't cropped. Tiny
    embedded EXE icons are upscaled for consistent Qt QTreeWidget sizing.
    """
    with Image.open(path) as original:
        image = original.convert("RGBA")
    if image.width < 1 or image.height < 1:
        raise ValueError("Empty image")
    # Ignore barely-visible transparent pixels when measuring the real icon.
    # A fallback keeps completely transparent/corrupt-looking assets safe.
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bbox:
        image = image.crop(bbox)
    max_draw = max(1, round(output_size * IMAGE_FILL))
    # Image.thumbnail() never enlarges tiny 16px EXE icons; resize explicitly.
    factor = min(max_draw / image.width, max_draw / image.height)
    new_size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    image = image.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((output_size - image.width) // 2,
                                   (output_size - image.height) // 2))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


@lru_cache(maxsize=512)
def _cached_normalized_icon(path_str: str, mtime_ns: int, file_size: int,
                            ctime_ns: int, inode: int, device: int) -> bytes:
    # Using mtime and size as cache keys makes regenerated/changed art refresh.
    return normalized_icon_png(Path(path_str))


def game_art_icon(path: Path, fallback):
    """Return a large, consistently framed QIcon, with safe fallback.

    Qt is imported only when the GUI requests an icon. The source art is kept
    untouched, and the normalized result is cached in memory by timestamp.
    """
    try:
        from ui.widgets.artwork_cache import file_revision, cached_pixmap
        revision = file_revision(path)
        if revision is None:
            return fallback
        from PySide6.QtGui import QIcon, QPixmap
        def load():
            png_bytes = _cached_normalized_icon(*revision)
            pix = QPixmap()
            pix.loadFromData(png_bytes, "PNG")
            return pix
        pix = cached_pixmap(revision, ("normalized-icon", NORMALIZED_SIZE), load)
        if not pix.isNull():
            return QIcon(pix)
    except (OSError, ValueError, ImportError, RuntimeError):
        pass
    return fallback
