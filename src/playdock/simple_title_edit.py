"""Reversible per-game display-title edits shared by simple and detailed UI.

Changes only metadata in the application's cache. Never renames, moves,
opens, or modifies any game binary, archive, folder, or collection.
"""
from __future__ import annotations

from core import Game, Library

MAX_TITLE_HISTORY = 20
SNAPSHOT_FIELDS = ("title", "prefer_manual_title", "title_source", "title_product_code")


def title_history(library: Library, game: Game) -> list[dict]:
    raw = library.meta(game).get("title_history", [])
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict) and all(key in x for key in SNAPSHOT_FIELDS)][-MAX_TITLE_HISTORY:]


def _snapshot(meta: dict) -> dict:
    return {key: meta.get(key) for key in SNAPSHOT_FIELDS}


def save_display_title(library: Library, game: Game, title: str,
                       *, source: str = "사용자 직접 수정") -> bool:
    """Save a manual title and append a durable undo point; return changed flag."""
    title = title.strip()
    if not title or len(title) > 240 or any(ord(c) < 32 for c in title):
        raise ValueError("게임 이름은 줄바꿈 없이 1~240자로 입력해 주세요.")
    if library.base_title(game) == title and library.meta(game).get("prefer_manual_title") is True:
        return False
    if library.title(game) == title and not library.meta(game).get("prefer_manual_title"):
        # Existing localized name already matches; no need to override it.
        return False
    meta = library.meta(game)
    before = _snapshot(meta)
    history = title_history(library, game)
    history.append(before)
    library.update_meta(game, title=title, prefer_manual_title=True,
                        title_source=source, title_product_code='',
                        title_history=history[-MAX_TITLE_HISTORY:])
    return True


def undo_display_title(library: Library, game: Game) -> bool:
    """Restore one previous display-title state (persists across launches)."""
    history = title_history(library, game)
    if not history:
        return False
    previous = history.pop()
    library.update_meta(game, **previous, title_history=history)
    return True


def restore_filename_title(library: Library, game: Game) -> bool:
    """Show the raw archive/folder stem again; remains reversible with Undo."""
    return save_display_title(library, game, game.name, source="원본 파일명으로 복원")
