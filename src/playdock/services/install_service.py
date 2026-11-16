"""Install to staging and move approved installed folders to the recycle bin.

Only this service publishes extracted files or removes an installed folder.
Original archives and manually registered external games must remain untouched.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable
import os
import shutil
import stat
import tempfile
from models.game import Game, safe_folder_name
from services.archive_service import (
    ArchivePasswordRequired, ArchivePasswordInvalid, archive_requires_password,
    _unpack_zip, _unpack_7z, _unpack_rar,
)


def install(game: Game, progress: Callable[[int], None] | None = None,
            password: str | None = None) -> Path:
    """Extract into staging and only publish a complete installation."""
    if game.archive is None:
        raise FileNotFoundError('설치할 압축파일이 없습니다.')
    if game.installed:
        raise FileExistsError('이미 압축을 푼 게임 폴더가 있습니다.')
    progress = progress or (lambda n: None)
    root = game.root
    if not root.is_dir():
        raise FileNotFoundError('라이브러리 폴더를 찾을 수 없습니다.')
    target = root / safe_folder_name(game.archive.stem)
    if target.exists():
        raise FileExistsError(f'설치 대상 폴더가 이미 존재합니다: {target}')
    # Avoid creating a staging directory if the encrypted archive has no password.
    if password is None and archive_requires_password(game.archive):
        raise ArchivePasswordRequired('이 압축파일은 비밀번호가 필요합니다.')
    stage = Path(tempfile.mkdtemp(prefix='.localgameshelf-staging-', dir=root))
    try:
        ext = game.archive.suffix.lower()
        if ext == '.zip':
            _unpack_zip(game.archive, stage, progress, password=password)
        elif ext == '.7z':
            _unpack_7z(game.archive, stage, progress, password=password)
        elif ext == '.rar':
            _unpack_rar(game.archive, stage, progress, password=password)
        else:
            raise ValueError('지원하지 않는 압축 형식입니다.')
        entries = list(stage.iterdir())
        if not entries:
            raise ValueError('압축파일이 비어 있습니다.')
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else stage
        if target.exists():
            raise FileExistsError('설치 중 다른 프로세스가 대상 폴더를 만들었습니다.')
        source.rename(target)
        progress(100)
        return target
    finally:
        shutil.rmtree(stage, ignore_errors=True)

def uninstall_target(game: Game, archive_root: Path | None = None) -> Path:
    """Validate a single installed top-level game directory before sending it to trash.

    Never allow the library directory, a linked/junction directory, or a directory
    that contains the configured archive source to be removed. No recursive
    deletion is performed here.
    """
    if game.external:
        raise ValueError('수동 등록한 외부 게임은 삭제하지 않습니다. 연결 해제를 사용하세요.')
    folder = game.folder
    if folder is None or not folder.is_dir():
        raise FileNotFoundError("설치된 게임 폴더를 찾을 수 없습니다.")
    root = game.root
    if not root.is_dir():
        raise FileNotFoundError("게임 설치 라이브러리 폴더를 찾을 수 없습니다.")

    # The selected library must be a dedicated directory, never the drive root
    # or the account's home directory.
    resolved_root = root.resolve(strict=True)
    if resolved_root == Path(resolved_root.anchor) or resolved_root == Path.home().resolve():
        raise ValueError("드라이브 최상위 또는 사용자 홈 폴더에서는 설치 제거를 허용하지 않습니다.")

    # Windows junctions are not always reported as symlinks on Python 3.10.
    # Moving them to trash could surprise users about what is actually moved.
    file_attrs = getattr(os.lstat(folder), "st_file_attributes", 0)
    reparse_bit = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if folder.is_symlink() or (file_attrs & reparse_bit) or getattr(folder, 'is_junction', lambda: False)():
        raise ValueError("링크 또는 정션으로 연결된 게임 폴더는 제거하지 않습니다.")

    target = folder.resolve(strict=True)
    if target.parent != resolved_root or target == resolved_root:
        raise ValueError("설치 라이브러리 바로 아래의 게임 폴더만 제거할 수 있습니다.")
    if target.is_mount():
        raise ValueError("별도 드라이브나 마운트 지점인 폴더는 제거하지 않습니다.")

    # Protect original archives even when the two configured locations overlap
    # or one was subsequently moved inside the game's folder.
    if archive_root is not None and Path(archive_root).resolve().is_relative_to(target):
        raise ValueError("압축파일 보관 폴더가 게임 폴더 안에 있어 제거할 수 없습니다.")
    if game.archive is not None and Path(game.archive).resolve().is_relative_to(target):
        raise ValueError("원본 압축파일이 게임 폴더 안에 있어 제거할 수 없습니다.")
    return target

def uninstall_to_recycle_bin(game: Game, archive_root: Path | None = None,
                             move_to_trash: Callable[[str], None] | None = None) -> Path:
    """Move one installed game folder to the OS recycle bin; never permanently delete.

    Callers must obtain explicit confirmation before invoking this function.
    The injected mover makes the safety policy testable without touching the
    user's real recycle bin.
    """
    target = uninstall_target(game, archive_root)
    if move_to_trash is None:
        try:
            from send2trash import send2trash
        except ImportError as exc:
            raise RuntimeError("설치 제거 기능에 send2trash가 필요합니다. 최신 버전으로 업데이트해 주세요.") from exc
        move_to_trash = send2trash
    move_to_trash(str(target))
    if target.exists():
        raise OSError("휴지통 이동 후에도 게임 설치 폴더가 남아 있습니다. 다시 확인해 주세요.")
    return target
