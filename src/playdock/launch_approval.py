"""Persist a user's one-time approval of their selected game executable.

The approval is scoped to one game (its metadata file) and to one relative EXE
path inside that game's install directory. It does not authorize arbitrary
processes or executables outside the install directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

APPROVED_EXE_KEY = "launch_confirmed_executable"


def executable_identity(game_folder: Path, executable: Path) -> str:
    """Return a stable per-installation relative path; reject escapes/non-EXEs."""
    root = Path(game_folder).resolve(strict=True)
    path = Path(executable).resolve(strict=True)
    if not root.is_dir() or not path.is_file() or path.suffix.casefold() != ".exe":
        raise ValueError("설치 폴더 안의 유효한 EXE 파일만 실행할 수 있습니다.")
    if not path.is_relative_to(root):
        raise ValueError("게임 설치 폴더 밖의 EXE는 선택할 수 없습니다.")
    return path.relative_to(root).as_posix().casefold()


def needs_launch_confirmation(meta: Mapping[str, object], game_folder: Path,
                              executable: Path) -> bool:
    """Ask only if this exact relative executable has never been approved."""
    identity = executable_identity(game_folder, executable)
    return meta.get(APPROVED_EXE_KEY) != identity


def launch_approval_changes(game_folder: Path, executable: Path) -> dict[str, str]:
    """Write only after a user approved launching the EXE successfully."""
    return {APPROVED_EXE_KEY: executable_identity(game_folder, executable)}


def executable_selection_changes(game_folder: Path, selected: str,
                                 meta: Mapping[str, object]) -> dict[str, object]:
    """Changing to another EXE makes the next run require a new approval."""
    candidate = (Path(game_folder) / selected).resolve(strict=True)
    identity = executable_identity(game_folder, candidate)
    changes: dict[str, object] = {"executable": selected}
    if meta.get(APPROVED_EXE_KEY) != identity:
        changes[APPROVED_EXE_KEY] = None
    return changes
