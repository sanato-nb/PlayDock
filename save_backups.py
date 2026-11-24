"""Manual save-folder backups. Does not infer save locations or touch games.

Restore always creates a fresh subfolder; original saves are never overwritten.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from hashlib import sha256
import json
import os
import stat
import tempfile
import zipfile

MAX_FILES = 150_000
MAX_TOTAL = 20 * 1024**3
CHUNK = 2 * 1024**2
FORMAT = 'PlayDockSaveBackup'
LEGACY_FORMAT = 'LocalGameShelfSaveBackup'


def _linked(path: Path) -> bool:
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        return True
    try:
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
    except OSError:
        return True


def _name(value: str) -> str:
    from core import safe_folder_name
    return safe_folder_name(value)[:65]


def create_save_backup(source: Path, destination_folder: Path, title: str, game_id: str) -> Path:
    source = Path(source).expanduser()
    if not source.is_dir() or _linked(source):
        raise ValueError('존재하는 일반 세이브 폴더를 선택해 주세요. 링크 폴더는 지원하지 않습니다.')
    source = source.resolve(strict=True)
    destination_folder = Path(destination_folder).expanduser().resolve()
    if destination_folder == source or destination_folder.is_relative_to(source):
        raise ValueError('백업 대상 폴더 안에 백업 ZIP을 저장할 수 없습니다.')
    destination_folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    outfile = destination_folder / f'{_name(title)}_save_{timestamp}.zip'
    saved, total = [], 0
    for base, dirs, names in os.walk(source, followlinks=False):
        here = Path(base)
        if _linked(here):
            raise ValueError('세이브 폴더에 링크가 포함되어 있어 백업하지 않습니다.')
        for folder in dirs:
            if _linked(here / folder):
                raise ValueError('링크된 폴더는 백업하지 않습니다.')
        for name in names:
            file = here / name
            if _linked(file) or not file.is_file():
                raise ValueError('일반 파일이 아닌 항목이 있어 백업하지 않습니다.')
            size = file.stat().st_size
            total += size
            if total > MAX_TOTAL or len(saved) >= MAX_FILES:
                raise ValueError('세이브 백업의 파일 수 또는 총 크기 안전 제한을 초과했습니다.')
            saved.append((file, file.relative_to(source).as_posix()))
    if not saved:
        raise ValueError('선택한 폴더에 백업할 파일이 없습니다.')
    fd, staging = tempfile.mkstemp(prefix='.lgs-save-', suffix='.zip', dir=destination_folder)
    os.close(fd)
    try:
        with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=4,
                             allowZip64=True) as zf:
            zf.writestr('manifest.json', json.dumps({
                'format': FORMAT, 'version': 1, 'game_id': game_id,
                'title': title, 'source_hint': str(source), 'files': len(saved)
            }, ensure_ascii=False))
            for file, rel in saved:
                zf.write(file, f'files/{rel}')
        os.replace(staging, outfile)
        return outfile
    finally:
        if Path(staging).exists():
            Path(staging).unlink()


def restore_save_backup(archive: Path, destination_folder: Path) -> Path:
    """Extract into a NEW folder under destination_folder. Never overwrite saves."""
    from core import validate_archive_member
    archive = Path(archive)
    destination_folder = Path(destination_folder).expanduser()
    if not archive.is_file() or archive.suffix.lower() != '.zip':
        raise ValueError('세이브 백업 ZIP 파일을 선택해 주세요.')
    if not destination_folder.is_dir() or _linked(destination_folder):
        raise ValueError('복원할 상위 폴더는 일반 폴더여야 합니다.')
    destination_folder = destination_folder.resolve(strict=True)
    if archive.resolve().is_relative_to(destination_folder):
        # A ZIP inside the chosen folder is fine; it will not be modified.
        pass
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = json.loads(zf.read('manifest.json'))
        except (KeyError, ValueError, UnicodeError) as exc:
            raise ValueError('PlayDock 세이브 백업 파일이 아닙니다.') from exc
        if manifest.get('format') not in {FORMAT, LEGACY_FORMAT} or manifest.get('version') != 1:
            raise ValueError('지원하지 않는 백업 형식입니다.')
        members = [i for i in zf.infolist() if i.filename != 'manifest.json']
        if len(members) > MAX_FILES:
            raise ValueError('백업 파일 개수가 안전 제한을 초과했습니다.')
        total = 0
        files = []
        for item in members:
            parts = validate_archive_member(item.filename)
            if not parts or parts[0] != 'files' or len(parts) < 2:
                raise ValueError('지원하지 않는 백업 항목입니다.')
            unix_mode = item.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError('백업에 링크 파일이 포함되어 있습니다.')
            total += item.file_size
            if total > MAX_TOTAL or item.flag_bits & 1:
                raise ValueError('용량 제한을 초과했거나 암호화된 백업입니다.')
            files.append((item, parts[1:]))
        folder_name = '복원_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        temp_dir = Path(tempfile.mkdtemp(prefix='.lgs-restore-', dir=destination_folder))
        target = destination_folder / folder_name
        try:
            for item, parts in files:
                dest = temp_dir.joinpath(*parts)
                if not dest.resolve().is_relative_to(temp_dir.resolve()):
                    raise ValueError('백업 경로가 안전하지 않습니다.')
                if item.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item) as src, dest.open('xb') as out:
                    size = 0
                    while True:
                        block = src.read(CHUNK)
                        if not block:
                            break
                        size += len(block)
                        if size > item.file_size or size > MAX_TOTAL:
                            raise ValueError('백업 크기와 실제 데이터가 다릅니다.')
                        out.write(block)
            temp_dir.rename(target)
            return target
        finally:
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
