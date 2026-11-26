"""Reversible per-game display-title edits shared by simple and detailed UI.

Changes only metadata in the application's cache. Never renames, moves,
opens, or modifies any game binary, archive, folder, or collection.
"""
from __future__ import annotations

from core import Game, Library

MAX_TITLE_HISTORY = 20
SNAPSHOT_FIELDS = ("title", "prefer_manual_title", "title_source", "title_product_code")


def title_history(library: Library, game: Game, *, meta: dict | None = None) -> list[dict]:
    if meta is None:
        meta = library.meta(game)
    raw = meta.get("title_history", [])
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict) and all(key in x for key in SNAPSHOT_FIELDS)][-MAX_TITLE_HISTORY:]


def _snapshot(meta: dict) -> dict:
    return {key: meta.get(key) for key in SNAPSHOT_FIELDS}


def localized_title_changes(meta: dict, title: str, language: str, source: str) -> dict:
    """Build one language update without writing or destroying other variants."""
    from services.localized_titles import LANGUAGES, language_is_plausible
    from product_titles import clean_title
    title = clean_title(title)
    if language not in LANGUAGES or not title or not language_is_plausible(title, language):
        raise ValueError("선택 언어와 제목의 문자가 일치하지 않습니다.")
    variants = dict(meta.get("localized_titles") or {})
    sources = dict(meta.get("localized_sources") or {})
    variants[language] = title
    sources[language] = source
    return dict(localized_titles=variants, localized_sources=sources, prefer_manual_title=False)


def save_localized_display_title(library: Library, game: Game, title: str,
                                 language: str, source: str) -> bool:
    """All localized edits share the same validation and reversible history."""
    meta = library.meta(game)
    changes = localized_title_changes(meta, title, language, source)
    if all(meta.get(key) == value for key, value in changes.items()):
        return False
    snapshot = _snapshot(meta)
    snapshot["localized_titles"] = dict(meta.get("localized_titles") or {})
    snapshot["localized_sources"] = dict(meta.get("localized_sources") or {})
    history = title_history(library, game, meta=meta)
    history.append(snapshot)
    library.update_meta(game, **changes, title_history=history[-MAX_TITLE_HISTORY:])
    return True


def save_display_title(library: Library, game: Game, title: str,
                       *, source: str = "사용자 직접 수정") -> bool:
    """Save a manual title and append a durable undo point; return changed flag."""
    title = title.strip()
    if not title or len(title) > 240 or any(ord(c) < 32 for c in title):
        raise ValueError("게임 이름은 줄바꿈 없이 1~240자로 입력해 주세요.")
    meta = library.meta(game)
    base, displayed = library.title_pair(game, meta=meta)
    if base == title and meta.get("prefer_manual_title") is True:
        return False
    if displayed == title and not meta.get("prefer_manual_title"):
        # Existing localized name already matches; no need to override it.
        return False
    before = _snapshot(meta)
    history = title_history(library, game, meta=meta)
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


def original_display_name(library: Library, game: Game, *, meta: dict | None = None) -> str:
    """Use one safe first-seen basename rule for preview and restore."""
    from pathlib import Path
    if meta is None:
        meta = library.meta(game)
    remembered = meta.get("original_archive_name")
    return Path(remembered).stem if isinstance(remembered, str) and (
        remembered.casefold().endswith((".zip", ".7z", ".rar"))
        and "/" not in remembered and "\\" not in remembered
    ) else game.name


def restore_filename_title(library: Library, game: Game) -> bool:
    """Restore only the displayed name; never rename the archive."""
    return save_display_title(library, game, original_display_name(library, game),
                              source="최초 압축파일명으로 복원")
