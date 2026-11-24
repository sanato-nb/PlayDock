"""Find probable game executables without running installers or updates."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import os
import re
from models.game import Game
if TYPE_CHECKING:
    from services.library_service import Library

BAD_EXE_WORDS = (
    "unins", "uninstall", "setup", "installer", "crashhandler", "crashreport",
    "redist", "vcredist", "dxsetup", "directx", "updater", "update", "patcher",
    "unitycrashhandler", "prereq", "eac_launcher", "easyanticheat", "dotnet",
)


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
