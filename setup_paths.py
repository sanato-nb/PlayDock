"""First-run and installer paths. Standard library only, safe to import by setup.exe."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def config_path() -> Path:
    from local_storage import data_dir
    return data_dir() / 'settings.json'


def proposed_paths() -> tuple[Path, Path]:
    docs = Path.home() / "Documents"
    return docs / "game_archives", docs / "game"


def normalize_paths(archive_text: str, game_text: str) -> tuple[Path, Path]:
    if not archive_text.strip() or not game_text.strip():
        raise ValueError("두 폴더를 모두 지정해 주세요.")
    archive = Path(os.path.expandvars(os.path.expanduser(archive_text.strip()))).absolute()
    game = Path(os.path.expandvars(os.path.expanduser(game_text.strip()))).absolute()
    if archive == game:
        raise ValueError("압축파일 폴더와 게임 설치 폴더는 서로 달라야 합니다.")
    for folder in (archive, game):
        if folder == Path(folder.anchor):
            raise ValueError("드라이브 최상위 경로는 선택하지 말아 주세요.")
        if folder.exists() and not folder.is_dir():
            raise ValueError(f"폴더 대신 파일이 있습니다: {folder}")
    return archive, game


def save_folder_settings(archive_text: str, game_text: str, store_path: Path | None = None) -> tuple[Path, Path]:
    """Create/check both directories and atomically preserve existing settings."""
    archive, game = normalize_paths(archive_text, game_text)
    for folder in (archive, game):
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".write-check-", dir=folder, delete=True):
            pass
    destination = store_path or config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    try:
        with destination.open("r", encoding="utf-8") as reader:
            value = json.load(reader)
            if isinstance(value, dict):
                existing = value
    except (OSError, json.JSONDecodeError):
        pass
    existing.update({"library": str(game), "archives": str(archive),
                     "first_run_complete": True, "auto_art": False})
    # Create on the same volume for atomic replace.
    descriptor, temporary = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as writer:
            json.dump(existing, writer, ensure_ascii=False, indent=2)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return archive, game
