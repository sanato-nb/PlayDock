"""Manage local archive scanning, installation paths, per-game cache and titles."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
from models.game import Game, game_key, safe_folder_name
from services.archive_service import ARCHIVE_EXT
from services.launch_service import has_executable_candidate


def data_dir() -> Path:
    from storage.local import data_dir as app_data_dir
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
        value = self.settings["library"] if "library" in self.settings else default_library()
        return Path(str(value)).expanduser()

    @property
    def archive_root(self) -> Path:
        value = self.settings["archives"] if "archives" in self.settings else self.root
        return Path(str(value)).expanduser()

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
                if not has_executable_candidate(child):
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
        meta = self.meta(game)
        return self._base_title_from_meta(game, meta, self._product_code_from_meta(game, meta))

    def _base_title_from_meta(self, game: Game, meta: dict, code: str) -> str:
        from services.localized_titles import localized_title_for
        translated = localized_title_for(meta, self.settings, original_name=game.name,
                                          product_code=code)
        # A title explicitly saved in the simple editor wins over cached
        # localized suggestions, without deleting those language variants.
        if meta.get("prefer_manual_title") is True and meta.get("title"):
            return str(meta["title"])
        if translated:
            return translated
        return str(meta.get("title") or game.name)

    def product_code(self, game: Game) -> str:
        return self._product_code_from_meta(game, self.meta(game))

    @staticmethod
    def _product_code_from_meta(game: Game, meta: dict) -> str:
        from models.game_codes import effective_product_code
        return effective_product_code(meta, game.name,
                                      game.archive.name if game.archive else '')

    def set_product_code(self, game: Game, code: str | None) -> None:
        from models.game_codes import normalize_code
        # An explicit blank overrides any guessed/file-name code, but does not
        # delete the game or affect archive names, installs, or collections.
        self.update_meta(game, product_code=normalize_code(code))

    def title(self, game: Game) -> str:
        from models.game_codes import title_with_code
        meta = self.meta(game)
        code = self._product_code_from_meta(game, meta)
        return title_with_code(self._base_title_from_meta(game, meta, code), code)
