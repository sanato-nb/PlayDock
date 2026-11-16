"""PlayDock: local library, safe extraction, per-game cache."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from typing import Callable

APP_NAME = "PlayDock"
MAX_FILES = 120_000
MAX_EXTRACTED_BYTES = 80 * 1024**3  # 80 GiB hard limit
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

BAD_EXE_WORDS = (
    "unins", "uninstall", "setup", "installer", "crashhandler", "crashreport",
    "redist", "vcredist", "dxsetup", "directx", "updater", "update", "patcher",
    "unitycrashhandler", "prereq", "eac_launcher", "easyanticheat", "dotnet",
)


def data_dir() -> Path:
    from local_storage import data_dir as app_data_dir
    return app_data_dir()


def default_library() -> Path:
    choices = [Path.home() / "Documents" / "game", Path.home() / "문서" / "game"]
    return next((x for x in choices if x.is_dir()), choices[0])


def load_json(path: Path, default: dict | None = None) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else (default or {})
    except (OSError, ValueError, TypeError):
        return dict(default or {})


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def game_key(name: str) -> str:
    """Pair an archive and a top-level folder with the same name (case-insensitive)."""
    return re.sub(r"\s+", " ", name.strip()).casefold()


def safe_folder_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name or name.casefold() in {"con", "prn", "aux", "nul"}:
        name = "game_" + sha256(name.encode()).hexdigest()[:8]
    return name[:130]


@dataclass
class Game:
    key: str
    name: str
    root: Path
    archive: Path | None = None
    folder: Path | None = None
    external: bool = False  # Manually linked game; never uninstall its folder.

    @property
    def id(self) -> str:
        if self.external:
            return sha256(('external|' + self.key).encode('utf-8')).hexdigest()[:22]
        return sha256((str(self.root.resolve()).casefold() + "|" + self.key).encode("utf-8")).hexdigest()[:22]

    @property
    def installed(self) -> bool:
        return self.folder is not None and self.folder.is_dir()

    @property
    def status(self) -> str:
        if self.installed:
            return "설치됨"
        if self.archive:
            return "설치 가능"
        return "경로 없음"


class Library:
    def __init__(self, store: Path | None = None):
        self.store = store or data_dir()
        self.config_path = self.store / "settings.json"
        existing = load_json(self.config_path)
        if existing:
            # v0.1.1 stored both archives and games under `library`. Keep the old
            # folder as the archive source until the user explicitly changes it.
            self.settings = dict(existing)
            self.settings.setdefault("archives", self.settings.get("library", str(default_library())))
            self.settings.setdefault("library", str(default_library()))
            self.settings.setdefault("auto_art", False)
        else:
            self.settings = {
                "library": str(default_library()),
                "archives": str(default_library().parent / "game_archives"),
                "auto_art": False,
            }
        self.manual_path = self.store / "manual_games.json"
        self.cache = self.store / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Installation directory; used to keep pre-v0.1.2 game cache IDs stable."""
        return Path(str(self.settings.get("library", default_library()))).expanduser()

    @property
    def archive_root(self) -> Path:
        return Path(str(self.settings.get("archives", self.root))).expanduser()

    def change_root(self, path: Path) -> None:
        if not path.is_dir():
            raise ValueError("게임 설치 폴더가 존재하지 않습니다.")
        self.settings["library"] = str(path.resolve())
        self.save_settings()

    def change_archive_root(self, path: Path) -> None:
        if not path.is_dir():
            raise ValueError("압축파일 보관 폴더가 존재하지 않습니다.")
        self.settings["archives"] = str(path.resolve())
        self.save_settings()

    def save_settings(self) -> None:
        save_json(self.config_path, self.settings)

    def scan(self) -> list[Game]:
        root = self.root
        archive_root = self.archive_root
        games: dict[str, Game] = {}
        if archive_root.is_dir():
            for child in sorted(archive_root.iterdir(), key=lambda c: c.name.casefold()):
                if (child.is_symlink() or not child.is_file() or
                        child.name.startswith(".") or child.suffix.lower() not in ARCHIVE_EXT):
                    continue
                key = game_key(child.stem)
                game = games.setdefault(key, Game(key, child.stem, root))
                # Prefer ZIP over 7z if both have identical stems.
                if game.archive is None or child.suffix.lower() == ".zip":
                    game.archive = child
        if root.is_dir():
            for child in sorted(root.iterdir(), key=lambda c: c.name.casefold()):
                if child.is_symlink() or not child.is_dir() or child.name.startswith("."):
                    continue
                if child.name in {"$RECYCLE.BIN", "System Volume Information"}:
                    continue
                # Ignore unrelated folders such as `file`, `saves`, or `screenshots`.
                # Folders with at least one plausible game EXE are registered.
                if not executable_candidates(child, child.name):
                    continue
                key = game_key(child.name)
                game = games.setdefault(key, Game(key, child.name, root))
                game.folder = child
                game.name = child.name
        # Keep manually registered EXEs independent of the scanned installation root.
        # Never run or delete files from a manual registration during scanning.
        registered = load_json(self.manual_path).get('games', [])
        if isinstance(registered, list):
            installed_paths = {g.folder.resolve() for g in games.values() if g.folder and g.folder.is_dir()}
            for entry in registered[:2000]:
                if not isinstance(entry, dict):
                    continue
                raw = entry.get('exe')
                if not isinstance(raw, str):
                    continue
                exe = Path(raw).expanduser()
                if not exe.is_file() or exe.suffix.casefold() != '.exe':
                    continue
                exe = exe.resolve()
                if exe.parent in installed_paths:
                    continue
                key = 'manual-' + sha256(str(exe).casefold().encode('utf-8')).hexdigest()[:20]
                title = entry.get('name') if isinstance(entry.get('name'), str) else exe.parent.name
                item = Game(key, title[:180], root, folder=exe.parent, external=True)
                games[key] = item
        return sorted(games.values(), key=lambda g: g.name.casefold())

    def add_manual_executable(self, executable: Path) -> Game:
        exe = Path(executable).expanduser().resolve(strict=True)
        if not exe.is_file() or exe.suffix.casefold() != '.exe':
            raise ValueError('등록할 파일은 존재하는 .exe 파일이어야 합니다.')
        existing = load_json(self.manual_path).get('games', [])
        records = existing if isinstance(existing, list) else []
        if any(isinstance(x, dict) and str(x.get('exe', '')).casefold() == str(exe).casefold() for x in records):
            raise ValueError('이미 수동 등록된 실행 파일입니다.')
        if any(g.folder is not None and g.folder.resolve() == exe.parent
               for g in self.scan() if not g.external):
            raise ValueError('이 게임 폴더는 이미 라이브러리에서 자동 인식되고 있습니다.')
        if len(records) >= 2000:
            raise ValueError('수동 등록 최대 개수를 초과했습니다.')
        game = Game('manual-' + sha256(str(exe).casefold().encode('utf-8')).hexdigest()[:20],
                    exe.parent.name, self.root, folder=exe.parent, external=True)
        records.append({'exe': str(exe), 'name': game.name})
        save_json(self.manual_path, {'games': records})
        self.update_meta(game, executable=exe.name)
        return game

    def remove_manual_executable(self, game: Game) -> bool:
        if not game.external or game.folder is None:
            raise ValueError('수동 등록 게임만 라이브러리에서 연결 해제할 수 있습니다.')
        data = load_json(self.manual_path).get('games', [])
        records = data if isinstance(data, list) else []
        kept = []
        for record in records:
            if not isinstance(record, dict):
                continue
            exe = Path(str(record.get('exe', '')))
            key = 'manual-' + sha256(str(exe).casefold().encode('utf-8')).hexdigest()[:20]
            if key != game.key:
                kept.append(record)
        if len(kept) == len(records):
            return False
        save_json(self.manual_path, {'games': kept})
        return True

    def kind(self, game: Game) -> str:
        """All entries are games. Ignore legacy category metadata for compatibility.

        Historical `category` fields remain untouched so upgrades are lossless,
        but no filename-based patch/DLC classification is performed.
        """
        return '게임'

    def art_dir(self, game: Game) -> Path:
        folder = self.cache / game.id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def meta(self, game: Game) -> dict:
        return load_json(self.art_dir(game) / "meta.json")

    def update_meta(self, game: Game, **changes: object) -> dict:
        data = self.meta(game)
        data.update(changes)
        save_json(self.art_dir(game) / "meta.json", data)
        return data

    def base_title(self, game: Game) -> str:
        """Raw user-visible name, without the optional product-code overlay."""
        from localized_titles import localized_title_for
        meta = self.meta(game)
        translated = localized_title_for(meta, self.settings, original_name=game.name,
                                          product_code=self.product_code(game))
        # A title explicitly saved in the simple editor wins over cached
        # localized suggestions, without deleting those language variants.
        if meta.get("prefer_manual_title") is True and meta.get("title"):
            return str(meta["title"])
        if translated:
            return translated
        return str(meta.get("title") or game.name)

    def product_code(self, game: Game) -> str:
        from game_codes import effective_product_code
        meta = self.meta(game)
        return effective_product_code(meta, game.name,
                                      game.archive.name if game.archive else '')

    def set_product_code(self, game: Game, code: str | None) -> None:
        from game_codes import normalize_code
        # An explicit blank overrides any guessed/file-name code, but does not
        # delete the game or affect archive names, installs, or collections.
        self.update_meta(game, product_code=normalize_code(code))

    def title(self, game: Game) -> str:
        from game_codes import title_with_code
        return title_with_code(self.base_title(game), self.product_code(game))


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


def executable_candidates(folder: Path, title: str = "") -> list[Path]:
    """Find plausible game EXEs; never automatically launch an installer."""
    if not folder.is_dir():
        return []
    result: list[tuple[float, Path]] = []
    norm_title = re.sub(r"[^a-z0-9]", "", title.casefold())
    for base, dirs, files in os.walk(folder):
        basepath = Path(base)
        depth = len(basepath.relative_to(folder).parts)
        dirs[:] = [d for d in dirs if d.casefold() not in {
            "redist", "_redist", "__redist", "_commonredist", "directx", "support",
            "backup", "node_modules", ".git"}]
        if depth >= 5:
            dirs[:] = []
        for filename in files:
            if not filename.casefold().endswith(".exe"):
                continue
            low = filename.casefold()
            if any(word in low for word in BAD_EXE_WORDS):
                continue
            path = basepath / filename
            name = re.sub(r"[^a-z0-9]", "", path.stem.casefold())
            score = 100.0 - depth * 12
            if norm_title and name and (name in norm_title or norm_title in name):
                score += 130
            if name in {"game", "game64", "win64", "launcher", "start", "play"}:
                score += 25
            if "shipping" in low:
                score += 20
            try:
                score += min(32, path.stat().st_size / (15 * 1024**2))
            except OSError:
                pass
            result.append((score, path))
    result.sort(key=lambda pair: (-pair[0], str(pair[1]).casefold()))
    return [path for _, path in result]


def chosen_executable(library: Library, game: Game) -> Path | None:
    if not game.folder:
        return None
    meta = library.meta(game)
    selected = meta.get("executable")
    if isinstance(selected, str):
        path = (game.folder / selected).resolve()
        if path.is_relative_to(game.folder.resolve()) and path.is_file() and path.suffix.casefold() == ".exe":
            return path
    paths = executable_candidates(game.folder, library.title(game))
    return paths[0] if paths else None
