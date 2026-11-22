"""One-folder PlayDock renaming: a local, private AI mapping beside the EXE.

No user filenames or mapping are committed to GitHub. The mapping is supplied in
the user's downloaded ZIP only. Paths never leave the local computer. The user
selects one directory; files are scanned recursively, matched exactly by
basename, then officially re-verified before rename approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .rename_companion import ReviewRow, load_review
from .research_handoff import safe_rename, undo_last, default_journal

DATA_FILENAME = "PlayDock_Rename_Data.json"
MAX_FILES = 50000

@dataclass(frozen=True)
class FolderMatch:
    row: ReviewRow
    path: Path | None
    status: str           # ready / manual / missing / duplicate / collision
    detail: str = ""


def load_local_mapping(path: str | Path) -> tuple[list[ReviewRow], list[str]]:
    """One self-contained file containing the original exclusions and AI results."""
    return load_review(path, path)


def scan_archives(root: Path, limit: int = MAX_FILES) -> dict[str, list[Path]]:
    root = Path(root)
    if not root.is_dir():
        raise ValueError("유효한 폴더를 선택하세요.")
    found: dict[str, list[Path]] = {}
    visited = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        # Never enter directory symlinks or junctions/reparse points.
        dirs[:] = [n for n in dirs if not (Path(directory) / n).is_symlink()
                   and not (Path(directory) / n).is_junction()]
        for name in names:
            if Path(name).suffix.casefold() not in (".zip", ".7z", ".rar"):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            visited += 1
            if visited > limit:
                raise ValueError("압축파일이 너무 많아 안전을 위해 탐색을 중지했습니다.")
            found.setdefault(name, []).append(path)
    return found


def folder_plan(folder: str | Path, mappings: list[ReviewRow]) -> list[FolderMatch]:
    root = Path(folder)
    found = scan_archives(root)
    result: list[FolderMatch] = []
    for row in mappings:
        paths = found.get(row.filename, [])
        if not paths:
            result.append(FolderMatch(row, None, "missing", "선택 폴더에 파일 없음"))
            continue
        if len(paths) > 1:
            result.append(FolderMatch(row, None, "duplicate", "하위 폴더에 같은 이름의 파일이 여러 개 있음"))
            continue
        path = paths[0]
        if row.ai_status != "claimed_confirmed" or not row.suggestion:
            result.append(FolderMatch(row, path, "manual", "AI 미확인·후보·DLC/합본 · 사용자 수동 확인"))
            continue
        if row.proposed == row.filename:
            result.append(FolderMatch(row, path, "manual", "이미 품번 포함: 새 이름 불필요"))
            continue
        dest = path.with_name(row.proposed)
        if (dest.exists() or dest.is_symlink() or
                any(x.name.casefold() == dest.name.casefold()
                    for x in path.parent.iterdir())):
            result.append(FolderMatch(row, path, "collision", "변경할 이름의 파일이 이미 존재함"))
            continue
        result.append(FolderMatch(row, path, "ready", "공식 사이트 재조회 대기"))
    return result


def rename_verified(item: FolderMatch, *, journal: Path | None = None
                    ) -> tuple[Path, str]:
    if item.status != "ready" or item.path is None:
        raise ValueError("수동/미확인/충돌 파일은 자동 이름 변경할 수 없습니다.")
    return safe_rename(item.path, item.row.proposed, journal or default_journal())
