"""Safe bulk title plans for PlayDock.

Review happens before writing. Only per-game metadata is changed. Archives and
installed games are never opened, moved, or renamed. Backups precede all writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import json
import re
import zipfile

from core import Library, Game
from services.simple_title_edit import (
    MAX_TITLE_HISTORY, SNAPSHOT_FIELDS, title_history, save_display_title,
    restore_filename_title, undo_display_title,
)
from services.localized_titles import LANGUAGES, language_is_plausible


@dataclass
class BulkChange:
    game_id: str
    expected_name: str
    proposed_name: str
    method: str = "manual"  # manual | original | localized | undo
    language: str = "ko"
    source: str = "사용자 일괄 수정"
    product_code: str = ""


def replace_name(title: str, search: str, replacement: str, *, case_sensitive: bool = False) -> str:
    """Preview a literal (non-regex) replacement, without touching a file."""
    if not search:
        raise ValueError("찾을 단어나 문구를 입력해 주세요.")
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.sub(re.escape(search), lambda match: replacement, title, flags=flags).strip()


def name_was_manually_changed(library: Library, game: Game) -> bool:
    meta = library.meta(game)
    return bool(meta.get("prefer_manual_title")) or (
        bool(meta.get("title")) and meta.get("title") != game.name
    )


def _validate_name(name: str) -> str:
    title = name.strip()
    if not 1 <= len(title) <= 240 or any(ord(c) < 32 for c in title):
        raise ValueError("이름은 줄바꿈 없이 1~240자로 입력해 주세요.")
    return title


def validate_changes(library: Library, games: list[Game], changes: list[BulkChange]) -> list[tuple[Game, BulkChange]]:
    by_id = {game.id: game for game in games}
    validated = []
    seen = set()
    for change in changes:
        if change.game_id in seen:
            raise ValueError("같은 게임이 일괄 변경 목록에 중복되어 있습니다.")
        seen.add(change.game_id)
        game = by_id.get(change.game_id)
        if game is None:
            raise ValueError("게임 목록이 바뀌었습니다. 목록을 다시 조회해 주세요.")
        if library.title(game) != change.expected_name:
            raise ValueError(f"'{game.name}'의 이름이 미리보기 이후 변경됐습니다. 다시 미리보기를 만드세요.")
        if change.method not in ("manual", "original", "localized", "undo"):
            raise ValueError("지원하지 않는 일괄 변경 방식입니다.")
        if change.method not in ("original", "undo"):
            _validate_name(change.proposed_name)
        if change.method == "undo" and not title_history(library, game):
            raise ValueError(f"{game.name}: 이전 이름 이력이 없습니다.")
        if change.method == "localized":
            if change.language not in LANGUAGES:
                raise ValueError("저장할 표시 언어가 올바르지 않습니다.")
            if not language_is_plausible(change.proposed_name, change.language):
                raise ValueError(f"{game.name}: 선택 언어와 제목의 문자가 일치하지 않습니다.")
            if not change.product_code or library.product_code(game) != change.product_code:
                raise ValueError(f"{game.name}: 작품 코드가 변경됐거나 확인되지 않았습니다.")
        validated.append((game, change))
    return validated




def preview_undo_name(library: Library, game: Game) -> str | None:
    """Display the next undo target, including any prior localized title state."""
    history = title_history(library, game)
    if not history:
        return None
    previous = history[-1]
    old_meta = dict(library.meta(game), **previous)
    from services.localized_titles import localized_title_for
    from models.game_codes import title_with_code
    if old_meta.get('prefer_manual_title') and old_meta.get('title'):
        name = str(old_meta['title'])
    else:
        name = (localized_title_for(old_meta, library.settings, original_name=game.name,
                product_code=library.product_code(game)) or str(old_meta.get('title') or game.name))
    return title_with_code(name, library.product_code(game))

def _backup_meta(library: Library, pairs: list[tuple[Game, BulkChange]]) -> Path:
    folder = library.store / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = folder / f"title_bulk_{now.strftime('%Y%m%d_%H%M%S_%f')}.zip"
    manifest = {'format': 1, 'created_at': now.isoformat(), 'items': []}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for game, change in pairs:
            digest = sha256(game.id.encode('utf-8')).hexdigest()
            manifest['items'].append({'game_id': game.id, 'original_name': game.name,
                                      'before': change.expected_name, 'after': change.proposed_name,
                                      'meta_file': 'meta/' + digest + '.json'})
            zf.writestr('meta/' + digest + '.json', json.dumps(library.meta(game), ensure_ascii=False, indent=2))
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    return path


def _save_localized_with_history(library: Library, game: Game, change: BulkChange) -> bool:
    meta = library.meta(game)
    variants = dict(meta.get('localized_titles') or {})
    sources = dict(meta.get('localized_sources') or {})
    if variants.get(change.language) == change.proposed_name and not meta.get('prefer_manual_title'):
        return False
    # Simple-mode undo accepts extra snapshot fields and will restore them.
    snapshot = {key: meta.get(key) for key in SNAPSHOT_FIELDS}
    snapshot['localized_titles'] = dict(variants)
    snapshot['localized_sources'] = dict(sources)
    history = title_history(library, game)
    history.append(snapshot)
    variants[change.language] = change.proposed_name
    sources[change.language] = change.source
    library.update_meta(game, localized_titles=variants, localized_sources=sources,
                        prefer_manual_title=False, title_history=history[-MAX_TITLE_HISTORY:])
    return True


def apply_bulk_changes(library: Library, games: list[Game], changes: list[BulkChange]) -> tuple[int, Path | None]:
    """Apply reviewed items with a timestamped backup and rollback on write error."""
    validated = validate_changes(library, games, changes)
    if not validated:
        return 0, None
    backup = _backup_meta(library, validated)
    original_bytes: list[tuple[Path, bytes | None]] = []
    updated = 0
    try:
        for game, change in validated:
            meta_file = library.art_dir(game) / 'meta.json'
            original_bytes.append((meta_file, meta_file.read_bytes() if meta_file.is_file() else None))
            if change.method == 'original':
                applied = restore_filename_title(library, game)
            elif change.method == 'undo':
                applied = undo_display_title(library, game)
            elif change.method == 'localized':
                applied = _save_localized_with_history(library, game, change)
            else:
                applied = save_display_title(library, game, change.proposed_name, source=change.source)
            updated += bool(applied)
    except Exception:
        # Restore exactly the pre-change metadata. Do not touch archives/games.
        for meta_file, contents in reversed(original_bytes):
            try:
                if contents is None:
                    meta_file.unlink(missing_ok=True)
                else:
                    meta_file.write_bytes(contents)
            except OSError:
                pass
        raise
    return updated, backup
