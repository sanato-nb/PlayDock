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


def _iter_executable_paths(folder: Path):
    """Yield candidates using the same depth and exclusion rules for all callers."""
    if not folder.is_dir():
        return
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
            yield depth, low, basepath / filename


def has_executable_candidate(folder: Path) -> bool:
    """Only test existence; do not rank, stat every EXE or walk past a match."""
    return next(_iter_executable_paths(folder), None) is not None


def _scored_executables(folder: Path, title: str):
    """Share the original ranking between list and single-result callers."""
    norm_title = re.sub(r"[^a-z0-9]", "", title.casefold())
    for depth, low, path in _iter_executable_paths(folder):
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
        yield score, path


def _rank_key(pair):
    return -pair[0], str(pair[1]).casefold()


def executable_candidates(folder: Path, title: str = "") -> list[Path]:
    """Find plausible game EXEs; never automatically launch an installer."""
    return [path for _, path in sorted(_scored_executables(folder, title), key=_rank_key)]


def best_executable_candidate(folder: Path, title: str = "") -> Path | None:
    """Same first candidate without allocating or sorting the full result list."""
    best = min(_scored_executables(folder, title), key=_rank_key, default=None)
    return best[1] if best is not None else None


def chosen_executable(library: Library, game: Game, *, meta: dict | None = None,
                      title: str | None = None, candidates: list[Path] | None = None) -> Path | None:
    if not game.folder:
        return None
    if meta is None:
        meta = library.meta(game)
    selected = meta.get("executable")
    if isinstance(selected, str):
        path = (game.folder / selected).resolve()
        if path.is_relative_to(game.folder.resolve()) and path.is_file() and path.suffix.casefold() == ".exe":
            return path
    if candidates is not None:
        return candidates[0] if candidates else None
    return best_executable_candidate(game.folder, library.title(game) if title is None else title)
