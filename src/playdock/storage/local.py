"""One-folder installed application storage and conservative legacy migration.

Frozen applications opt into colocated data only when the installer marker is
present beside the executable. Source checkouts use the old AppData location.
No archive, extracted game, OS credential, or arbitrary folder is migrated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

APP_NAME = 'PlayDock'
LEGACY_APP_NAME = 'LocalGameShelf'
INSTALL_MARKER = 'PlayDock.install.json'
MARKER_ID = 'playdock-installed-v1'
LEGACY_INSTALL_MARKER = 'LocalGameShelf.install.json'
LEGACY_MARKER_ID = 'local-game-shelf-installed-v1'
DATA_DIRECTORY = 'data'
ROOT_FILES = {'settings.json', 'collections.json', 'product_titles.json', 'manual_games.json', 'playdock.db'}
CACHE_FILES = {'meta.json', 'hero.png', 'icon.png'}
GAME_CACHE_ID = re.compile(r'^[a-f0-9]{22}$')


def legacy_data_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA')
    return (Path(base) if base else Path.home() / '.local' / 'share') / LEGACY_APP_NAME


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def marker_is_valid(program: Path) -> bool:
    """Accept both PlayDock and a genuine installed Local Game Shelf marker."""
    for name, marker_id in ((INSTALL_MARKER, MARKER_ID),
                            (LEGACY_INSTALL_MARKER, LEGACY_MARKER_ID)):
        marker = Path(program) / name
        if _redirected(marker) or not marker.is_file():
            continue
        try:
            data = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (isinstance(data, dict) and data.get('id') == marker_id
                and data.get('data_directory') == DATA_DIRECTORY):
            return True
    return False


def write_install_marker(program: Path) -> None:
    program = Path(program)
    path = program / INSTALL_MARKER
    if _redirected(path):
        raise ValueError('설치 표식 파일이 링크여서 설치할 수 없습니다.')
    payload = {'id': MARKER_ID, 'data_directory': DATA_DIRECTORY, 'version': '0.8.0'}
    fd, temp = tempfile.mkstemp(prefix='.lgs-install-', suffix='.tmp', dir=program)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as writer:
            json.dump(payload, writer, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def program_store(program: Path) -> Path:
    return Path(program) / DATA_DIRECTORY


def data_dir_for_executable(executable: Path, *, frozen: bool = True) -> Path:
    program = Path(executable).absolute().parent
    if frozen and marker_is_valid(program):
        return program_store(program)
    old = legacy_data_dir()
    return old if old.exists() else old.with_name(APP_NAME)


def data_dir() -> Path:
    return data_dir_for_executable(Path(sys.executable), frozen=bool(getattr(sys, 'frozen', False)))


def _migration_files(source: Path):
    source = Path(source)
    if not source.is_dir() or _redirected(source):
        return
    for name in sorted(ROOT_FILES):
        path = source / name
        if path.is_file() and not _redirected(path):
            yield Path(name), path
    cache = source / 'cache'
    if cache.is_dir() and not _redirected(cache):
        for folder in cache.iterdir():
            if not GAME_CACHE_ID.fullmatch(folder.name) or not folder.is_dir() or _redirected(folder):
                continue
            for name in sorted(CACHE_FILES):
                path = folder / name
                if path.is_file() and not _redirected(path):
                    yield Path('cache') / folder.name / name, path
    # Existing backups may be important to users. Migrate ZIP files only; do
    # not blindly copy arbitrary folder trees from AppData into an install dir.
    backups = source / 'backups'
    if backups.is_dir() and not _redirected(backups):
        for path in backups.iterdir():
            if path.is_file() and not _redirected(path) and path.suffix.casefold() == '.zip':
                yield Path('backups') / path.name, path


def migrate_legacy_data(destination: Path, sources: list[Path] | None = None) -> dict:
    """Non-destructive, repeatable migration. Existing destination files win.

    The original source is kept intact. Each copied file is written through a
    private temp file then atomically renamed. No symlinks/junctions followed.
    """
    dest = Path(destination)
    sources = sources if sources is not None else [legacy_data_dir()]
    if _redirected(dest) or (dest.exists() and not dest.is_dir()):
        raise ValueError('데이터 폴더가 일반 폴더가 아닙니다.')
    dest.mkdir(parents=True, exist_ok=True)
    count, skipped = 0, 0
    for raw_source in sources:
        source = Path(raw_source)
        if not source.is_dir() or _redirected(source) or source.resolve() == dest.resolve():
            continue
        for relative, file in _migration_files(source):
            target = dest / relative
            cursor = target
            while cursor != dest.parent:
                if _redirected(cursor):
                    raise ValueError('데이터 대상에 링크가 있어 이전을 중단했습니다.')
                cursor = cursor.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                skipped += 1
                continue
            fd, temporary = tempfile.mkstemp(prefix='.lgs-migration-', dir=target.parent)
            os.close(fd)
            try:
                shutil.copy2(file, temporary)
                # Do not overwrite files the user or another process created
                # in the destination after migration started.
                if not target.exists():
                    os.replace(temporary, target)
                    count += 1
                else:
                    skipped += 1
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    return {'copied': count, 'skipped': skipped}
