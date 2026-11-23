"""Safe inventory, export and recovery of PlayDock *application data*.

Game archives, extracted games and saves are never included or modified.
The game list is created by Library.scan(), not a separately persisted list.
Backup's library_snapshot.json is informational; source files are authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import json
import sqlite3
import os
import re
import tempfile
import zipfile

GAME_ID = re.compile(r"^[0-9a-f]{22}$")
FORMAT = "PlayDockDataBackup"
LEGACY_FORMAT = "LocalGameShelfDataBackup"
VERSION = 1
ROOT_FILES = {"settings.json", "collections.json", "product_titles.json", "manual_games.json", "playdock.db"}
CACHE_FILES = {"meta.json", "hero.png", "icon.png"}
MAX_FILES = 20000
MAX_JSON = 8 * 1024**2
MAX_DB = 128 * 1024**2
MAX_IMAGE = 32 * 1024**2
MAX_TOTAL = 1024**3


@dataclass(frozen=True)
class DataInventory:
    games: int
    installed: int
    archives: int
    collections: int
    collection_memberships: int
    missing_memberships: int
    metadata: int
    orphaned_metadata: int
    images: int
    image_bytes: int
    product_titles: int


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def _cache_folders(store: Path):
    root = store / 'cache'
    if not root.is_dir() or _redirected(root):
        return []
    return [f for f in root.iterdir() if f.is_dir() and not _redirected(f) and GAME_ID.fullmatch(f.name)]


def _data_paths(store: Path):
    """Whitelist actual program-owned files; never follow symlinks."""
    store = Path(store)
    if _redirected(store):
        raise ValueError('설정 폴더가 링크여서 백업할 수 없습니다.')
    for filename in sorted(ROOT_FILES):
        path = store / filename
        if path.is_file() and not _redirected(path):
            yield filename, path
    for folder in _cache_folders(store):
        for filename in sorted(CACHE_FILES):
            path = folder / filename
            if path.is_file() and not _redirected(path):
                yield f'cache/{folder.name}/{filename}', path


def inventory(library, games, collections) -> DataInventory:
    games = list(games)
    ids = {game.id for game in games}
    records = collections.list()
    entries = [gid for col in records for gid in col['game_ids']]
    folders = _cache_folders(library.store)
    meta = [f for f in folders if (f / 'meta.json').is_file() and not (f / 'meta.json').is_symlink()]
    image_count = 0
    image_bytes = 0
    for folder in folders:
        for kind in ('hero.png', 'icon.png'):
            p = folder / kind
            if p.is_file() and not p.is_symlink():
                image_count += 1
                try:
                    image_bytes += p.stat().st_size
                except OSError:
                    pass
    from core import load_json
    titles = load_json(library.store / 'product_titles.json')
    return DataInventory(
        games=len(games), installed=sum(bool(g.installed) for g in games),
        archives=sum(g.archive is not None for g in games),
        collections=len(records), collection_memberships=len(entries),
        missing_memberships=sum(gid not in ids for gid in entries),
        metadata=len(meta), orphaned_metadata=sum(f.name not in ids for f in meta),
        images=image_count, image_bytes=image_bytes, product_titles=len(titles),
    )


def _allowed(member: str) -> bool:
    if member in ROOT_FILES:
        return True
    parts = PurePosixPath(member).parts
    return len(parts) == 3 and parts[0] == 'cache' and GAME_ID.fullmatch(parts[1]) is not None and parts[2] in CACHE_FILES


def _validate_file(member: str, content: bytes):
    limit = MAX_IMAGE if member.endswith('.png') else MAX_DB if member == 'playdock.db' else MAX_JSON
    if len(content) > limit:
        raise ValueError(f'백업 파일 크기가 안전 제한을 초과했습니다: {member}')
    if member.endswith('.json'):
        try:
            raw = json.loads(content.decode('utf-8'))
            if not isinstance(raw, dict):
                raise ValueError('JSON 객체가 아닙니다.')
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f'백업 JSON이 올바르지 않습니다: {member}') from exc
    if member == 'playdock.db':
        if not content.startswith(b'SQLite format 3\0'):
            raise ValueError('작품 DB 파일 헤더가 올바르지 않습니다.')
        with tempfile.TemporaryDirectory(prefix='playdock-db-check-') as temp:
            file = Path(temp) / 'test.db'
            file.write_bytes(content)
            try:
                with closing(sqlite3.connect(f'file:{file}?mode=ro', uri=True)) as db:
                    version = db.execute('PRAGMA user_version').fetchone()[0]
                    ok = db.execute('PRAGMA quick_check').fetchone()[0]
                    names = {row[0] for row in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
                    if version > 3 or ok != 'ok' or not {'works', 'library_links'}.issubset(names):
                        raise ValueError('PlayDock 작품 DB 구조 또는 무결성이 잘못되었습니다.')
            except sqlite3.DatabaseError as exc:
                raise ValueError('작품 DB 파일이 손상되었습니다.') from exc
    # Deliberately do not attempt to decode images with PIL during restore;
    # paths and sizes are validated and originals can be preserved unchanged.


def backup_data(store: Path, games, destination: Path) -> int:
    """Export settings, collection records, per-game metadata/artwork.

    A snapshot of scanned game list is included as informational JSON only.
    Does not contain installed game data or API keys held in Windows keyring.
    """
    store, destination = Path(store), Path(destination)
    files = list(_data_paths(store))
    if len(files) > MAX_FILES:
        raise ValueError('백업 파일 수가 안전 제한을 초과했습니다.')
    snapshot = []
    for game in games:
        snapshot.append({'id': game.id, 'name': game.name, 'installed': bool(game.installed),
                         'archive': str(game.archive) if game.archive else None,
                         'folder': str(game.folder) if game.folder else None})
    manifest = {'format': FORMAT, 'version': VERSION,
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'note': 'Game list is a snapshot only. Restore will rescan disk.',
                'files': [name for name, _ in files]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(prefix='.lgs-backup-', suffix='.zip', dir=destination.parent)
    os.close(handle)
    try:
        total = 0
        with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as z:
            z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            z.writestr('library_snapshot.json', json.dumps(snapshot, ensure_ascii=False, indent=2))
            for name, path in files:
                size = path.stat().st_size
                limit = MAX_IMAGE if name.endswith('.png') else MAX_DB if name == 'playdock.db' else MAX_JSON
                if size > limit or size + total > MAX_TOTAL:
                    raise ValueError(f'파일 크기 제한 초과: {name}')
                if name.endswith(('.json', '.db')):
                    _validate_file(name, path.read_bytes())
                z.write(path, arcname=name)
                total += size
        os.replace(staging, destination)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    return len(files)


def inspect_backup(source: Path) -> list[str]:
    """Validate the *whole* backup before any disk mutation."""
    with zipfile.ZipFile(source) as z:
        entries = z.infolist()
        if len(entries) > MAX_FILES + 2:
            raise ValueError('백업 항목 수가 너무 많습니다.')
        names = [e.filename for e in entries]
        if len(set(names)) != len(names) or 'manifest.json' not in names:
            raise ValueError('백업 구조가 손상되었거나 중복 파일이 있습니다.')
        manifest_info = z.getinfo('manifest.json')
        if manifest_info.file_size > MAX_JSON:
            raise ValueError('백업 설명 파일이 너무 큽니다.')
        manifest = json.loads(z.read('manifest.json').decode('utf-8'))
        if manifest.get('format') not in {FORMAT, LEGACY_FORMAT} or manifest.get('version') != VERSION:
            raise ValueError('PlayDock 백업 형식이 아닙니다.')
        actual = [n for n in names if n not in {'manifest.json', 'library_snapshot.json'}]
        if sorted(actual) != sorted(manifest.get('files', [])):
            raise ValueError('백업 파일 목록이 일치하지 않습니다.')
        total = 0
        for info in entries:
            name = info.filename
            if name in ('manifest.json', 'library_snapshot.json'):
                if info.file_size > MAX_JSON:
                    raise ValueError('백업 설명 크기가 너무 큽니다.')
                if name == 'library_snapshot.json':
                    snapshot = json.loads(z.read(name).decode('utf-8'))
                    if not isinstance(snapshot, list):
                        raise ValueError('게임 목록 스냅샷 형식이 잘못되었습니다.')
                continue
            if not _allowed(name) or info.is_dir() or '\\' in name:
                raise ValueError(f'허용되지 않은 백업 경로: {name}')
            # Block ZIP Unix symlink entries, even if the filename is whitelisted.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f'링크 항목은 복원할 수 없습니다: {name}')
            limit = MAX_IMAGE if name.endswith('.png') else MAX_DB if name == 'playdock.db' else MAX_JSON
            if info.file_size > limit:
                raise ValueError(f'백업 항목이 너무 큽니다: {name}')
            total += info.file_size
            if total > MAX_TOTAL:
                raise ValueError('백업 전체 크기 제한을 초과했습니다.')
            _validate_file(name, z.read(name))
        return actual


def restore_data(store: Path, source: Path) -> tuple[int, Path]:
    """Restore backed-up files by merging them into app data.

    Always writes an automatic *pre-restore* backup before modifying anything.
    Does not delete files not present in archive. The caller should reload the
    Library and CollectionStore (and rescan) after successful completion.
    """
    store = Path(store)
    source = Path(source)
    if _redirected(store) or _redirected(store / 'cache'):
        raise ValueError('설정 폴더가 링크여서 복원을 중단했습니다.')
    names = inspect_backup(source)
    safety_dir = store / 'backups'
    if _redirected(safety_dir):
        raise ValueError('백업 저장 위치가 링크입니다.')
    safety_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safety = safety_dir / f'before_restore_{stamp}.zip'
    backup_data(store, [], safety)
    # Validate in a private staging directory before beginning the merge.
    with tempfile.TemporaryDirectory(prefix='lgs-restore-') as temp:
        staging = Path(temp)
        with zipfile.ZipFile(source) as z:
            for name in names:
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
        # Refuse existing symlinks and junctions so the backup can never write
        # through a redirected destination. Only explicitly allowed filenames.
        for name in names:
            target = store / name
            p = target
            while p != store:
                if _redirected(p):
                    raise ValueError('복원 경로에 링크 또는 정션이 있어 중단했습니다.')
                p = p.parent
        for name in names:
            target = store / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = (staging / name).read_bytes()
            temp_target = target.with_name(target.name + '.restore-tmp')
            try:
                temp_target.write_bytes(content)
                os.replace(temp_target, target)
            finally:
                if temp_target.exists():
                    temp_target.unlink()
    return len(names), safety
