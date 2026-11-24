"""Validate ZIP/7z/RAR members and safely extract into a staging directory.

Keep traversal, symlink and zip-bomb guards here; do not weaken for UI changes.
"""
from __future__ import annotations
from pathlib import Path, PurePosixPath
from typing import Callable
import os
import stat
import zipfile

MAX_FILES = 120_000
MAX_EXTRACTED_BYTES = 80 * 1024**3
BLOCK_SIZE = 2 * 1024**2
ARCHIVE_EXT = {".zip", ".7z", ".rar"}


class ArchivePasswordRequired(RuntimeError):
    """A protected archive needs a password supplied by its owner."""

class ArchivePasswordInvalid(RuntimeError):
    """The supplied archive password did not decrypt this archive."""

def archive_requires_password(archive: Path) -> bool:
    """Inspect archive metadata without extracting or changing any file."""
    suffix = archive.suffix.lower()
    if suffix == '.zip':
        with zipfile.ZipFile(archive, 'r') as zf:
            return any((member.flag_bits & 1) != 0 or member.compress_type == 99
                       for member in zf.infolist())
    if suffix == '.rar':
        try:
            import rarfile
            with rarfile.RarFile(archive) as rf:
                return bool(rf.needs_password())
        except ImportError as exc:
            raise RuntimeError('RAR 파일 확인을 위해 rarfile 설치가 필요합니다.') from exc
        except Exception as exc:
            if 'password' in str(exc).casefold():
                return True
            raise
    if suffix == '.7z':
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError('7z 지원을 위해 py7zr 설치가 필요합니다.') from exc
        # Header-encrypted archives might raise a PasswordRequired exception
        # during opening, before needs_password() can be queried.
        try:
            with py7zr.SevenZipFile(archive, mode='r') as zf:
                return bool(zf.needs_password())
        except Exception as exc:
            if 'password' in str(exc).casefold():
                return True
            raise
    return False

def validate_archive_member(name: str) -> tuple[str, ...]:
    if not name or "\x00" in name:
        raise ValueError("유효하지 않은 압축 항목입니다.")
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or name.startswith(("/", "\\")) or any(":" in part for part in path.parts):
        raise ValueError(f"절대 경로가 포함되어 있습니다: {name}")
    if ".." in path.parts:
        raise ValueError(f"상위 폴더를 참조하는 압축 항목: {name}")
    return tuple(p for p in path.parts if p not in ("", "."))

def _check_target(base: Path, parts: tuple[str, ...]) -> Path:
    if not parts:
        raise ValueError("빈 경로")
    target = base.joinpath(*parts)
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError("설치 위치 바깥으로 쓰기를 시도했습니다.")
    return target

def _unpack_zip(archive: Path, stage: Path, progress: Callable[[int], None],
                password: str | None = None) -> None:
    # The stdlib cannot read WinZip AES entries (ZIP method 99).
    # pyzipper handles both AES and normal ZIPs; only import for AES archives.
    with zipfile.ZipFile(archive) as probe:
        info = probe.infolist()
        is_aes = any(item.compress_type == 99 for item in info)
        encrypted = any(item.flag_bits & 1 for item in info) or is_aes
    if encrypted and password is None:
        raise ArchivePasswordRequired('이 ZIP은 암호화되어 있습니다. 압축파일 비밀번호를 입력해 주세요.')
    reader = zipfile.ZipFile
    if is_aes:
        try:
            import pyzipper
        except ImportError as exc:
            raise RuntimeError('AES ZIP 설치를 위해 pyzipper가 필요합니다. 최신 버전으로 다시 설치해 주세요.') from exc
        reader = pyzipper.AESZipFile
    with reader(archive, 'r') as zf:
        if password is not None:
            zf.setpassword(password.encode('utf-8'))
        files = zf.infolist()
        if len(files) > MAX_FILES:
            raise ValueError('압축 항목 수가 안전 제한을 초과했습니다.')
        total = sum(item.file_size for item in files)
        if total > MAX_EXTRACTED_BYTES:
            raise ValueError('압축 해제 후 크기가 80GiB를 초과합니다.')
        members: list[tuple[zipfile.ZipInfo, Path]] = []
        for item in files:
            parts = validate_archive_member(item.filename)
            if not parts:
                continue
            unix_type = (item.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(unix_type):
                raise ValueError('심볼릭 링크가 들어 있는 ZIP은 안전상 설치하지 않습니다.')
            members.append((item, _check_target(stage, parts)))
        done = 0
        try:
            for item, dest in members:
                if item.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(item, 'r') as src, dest.open('wb') as out:
                    while True:
                        chunk = src.read(BLOCK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        progress(min(99, int(done * 100 / max(1, total))))
        except RuntimeError as exc:
            if 'password' in str(exc).casefold():
                raise ArchivePasswordInvalid('압축파일 비밀번호가 올바르지 않습니다. 다시 확인해 주세요.') from exc
            raise
        except (ValueError, zipfile.BadZipFile) as exc:
            error = str(exc).casefold()
            if ('password' in error or 'hmac' in error) and encrypted:
                raise ArchivePasswordInvalid('비밀번호가 틀렸거나 암호화된 파일이 손상되었습니다.') from exc
            raise

def _unpack_7z(archive: Path, stage: Path, progress: Callable[[int], None],
               password: str | None = None) -> None:
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError('7z 지원을 위해 py7zr를 설치하세요: pip install py7zr') from exc
    try:
        with py7zr.SevenZipFile(archive, 'r', password=password) as zf:
            if zf.needs_password() and password is None:
                raise ArchivePasswordRequired('이 7z는 암호화되어 있습니다. 비밀번호를 입력해 주세요.')
            members = zf.list()
            if len(members) > MAX_FILES:
                raise ValueError('압축 항목 수가 안전 제한을 초과했습니다.')
            total = sum(int(getattr(f, 'uncompressed', 0) or 0) for f in members)
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError('압축 해제 후 크기가 80GiB를 초과합니다.')
            for item in members:
                parts = validate_archive_member(item.filename)
                if parts:
                    _check_target(stage, parts)
                if getattr(item, 'is_symlink', False):
                    raise ValueError('심볼릭 링크가 들어 있는 7z는 안전상 설치하지 않습니다.')
            progress(5)
            zf.extractall(path=stage)
        for path in stage.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(stage.resolve()):
                raise ValueError('안전하지 않은 압축 해제 결과입니다.')
    except Exception as exc:
        if isinstance(exc, (ArchivePasswordRequired, ArchivePasswordInvalid)):
            raise
        if 'password' in str(exc).casefold():
            if password is None:
                raise ArchivePasswordRequired('7z 비밀번호가 필요합니다.') from exc
            raise ArchivePasswordInvalid('7z 비밀번호가 틀렸거나 압축파일이 손상되었습니다.') from exc
        raise

def _unpack_rar(archive: Path, stage: Path, progress: Callable[[int], None],
                password: str | None = None) -> None:
    """Stream *validated* RAR entries through rarfile and an installed backend.

    rarfile reads metadata, but compressed RAR needs external UnRAR/7-Zip/unar.
    Never call RarFile.extractall() on an untrusted archive.
    """
    try:
        import rarfile
    except ImportError as exc:
        raise RuntimeError('RAR 지원을 위해 rarfile 라이브러리가 필요합니다.') from exc
    # rarfile's decompression tools are often installed outside PATH on Windows.
    if os.name == 'nt':
        for envvar, subfolder, attr in (
            ('ProgramFiles', 'WinRAR/UnRAR.exe', 'UNRAR_TOOL'),
            ('ProgramFiles', '7-Zip/7z.exe', 'SEVENZIP_TOOL'),
            ('ProgramFiles(x86)', '7-Zip/7z.exe', 'SEVENZIP_TOOL'),
        ):
            base = os.environ.get(envvar)
            if base:
                tool = Path(base) / subfolder
                if tool.is_file():
                    setattr(rarfile, attr, str(tool))
    try:
        with rarfile.RarFile(archive) as rf:
            if rf.needs_password() and password is None:
                raise ArchivePasswordRequired('RAR 압축파일 비밀번호가 필요합니다.')
            items = rf.infolist()
            if len(items) > MAX_FILES:
                raise ValueError('RAR 파일 수가 안전 제한을 초과했습니다.')
            total = sum(max(0, int(x.file_size)) for x in items)
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError('압축 해제 후 크기가 80GiB를 초과합니다.')
            validated = []
            for item in items:
                parts = validate_archive_member(item.filename)
                if not parts:
                    continue
                if (getattr(item, 'is_symlink', lambda: False)() or
                        getattr(item, 'file_redir', None) is not None or
                        stat.S_ISLNK(getattr(item, 'mode', 0) or 0)):
                    raise ValueError('링크/리디렉션이 포함된 RAR은 설치하지 않습니다.')
                validated.append((item, _check_target(stage, parts)))
            # Verify availability before creating any extracted payload.
            try:
                setup = getattr(rarfile, 'tool_setup', None)
                if setup is not None:
                    setup()
            except Exception as exc:
                raise RuntimeError('RAR 압축 해제 프로그램이 없습니다. 공식 7-Zip 또는 UnRAR를 설치하고 다시 시도하세요.') from exc
            done = 0
            for item, dest in validated:
                if item.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with rf.open(item, pwd=password) as src, dest.open('wb') as dst:
                    while True:
                        block = src.read(BLOCK_SIZE)
                        if not block:
                            break
                        done += len(block)
                        if done > MAX_EXTRACTED_BYTES:
                            raise ValueError('압축 해제 크기 제한을 초과했습니다.')
                        dst.write(block)
                        progress(min(99, int(done * 100 / max(1, total))))
    except Exception as exc:
        if isinstance(exc, (ArchivePasswordRequired, ArchivePasswordInvalid)):
            raise
        if 'password' in str(exc).casefold() or 'crypt' in str(exc).casefold():
            if password is None:
                raise ArchivePasswordRequired('RAR 비밀번호가 필요합니다.') from exc
            raise ArchivePasswordInvalid('RAR 비밀번호가 올바르지 않거나 파일이 손상됐습니다.') from exc
        raise
