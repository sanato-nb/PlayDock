"""Optional filename-only rename for *bare* DLsite/Steam IDs.

Independent of the AI-generated PowerShell renamer. Never decompress archives,
read their bytes, change PlayDock library data or make network requests.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import stat
import uuid

from .code_only import Result
from src.playdock.database.official_catalog import _valid_identity

BARE_DLSITE = re.compile(r"((?:RJ|VJ|BJ|EJ)\d{6,8})", re.I)
BARE_STEAM = re.compile(r"Steam[ \t_-]+([1-9]\d{2,9})", re.I)
BAD_TITLE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)
ARCHIVE_EXT = {".zip", ".7z", ".rar"}
JOURNAL_PREFIX = "playdock_autorename_"


def history_dir() -> Path:
    custom = os.environ.get("PLAYDOCK_AUTO_RENAME_HISTORY_DIR")
    if custom:
        return Path(custom).expanduser()
    if os.name == "nt":
        home = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return home / "PlayDock" / "AutoRenameHistory"


def bare_id(filename: str) -> tuple[str, str] | None:
    """Match only an ID, optionally wrapped in brackets, plus archive suffix."""
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    if ext not in ARCHIVE_EXT:
        return None
    stem = name[:-len(ext)].strip()
    if stem.startswith("[") and stem.endswith("]"):
        stem = stem[1:-1].strip()
    elif "[" in stem or "]" in stem:
        return None
    found = BARE_DLSITE.fullmatch(stem)
    if found:
        return "dlsite", found.group(1).upper()
    found = BARE_STEAM.fullmatch(stem)
    if found:
        return "steam", found.group(1)
    return None


def official_filename(title: str, store: str, code: str, ext: str) -> str | None:
    """Produce a Windows-safe filename, without guessing unrelated title details."""
    title = BAD_TITLE.sub(" ", title or "")
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title or title in {".", ".."} or RESERVED.fullmatch(title):
        return None
    tag = code if store == "dlsite" else f"Steam {code}"
    # Reserve room for code, extension, and an NTFS-friendly total filename.
    max_title = 180 - len(tag) - len(ext) - 3
    title = title[:max_title].rstrip(" .")
    if not title:
        return None
    name = f"{title} [{tag}]{ext}"
    if RESERVED.fullmatch(name):
        return None
    return name


def _check_root(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError("이름 변경할 폴더가 없거나 연결 폴더입니다.")
    return root.resolve(strict=True)


def _is_regular(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_junction():
            return False
        return stat.S_ISREG(path.stat(follow_symlinks=False).st_mode)
    except (OSError, ValueError):
        return False


def _archive_paths(root: Path, recursive: bool) -> list[Path]:
    result: list[Path] = []
    if recursive:
        for here, dirs, filenames in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(here) / d).is_symlink()
                       and not (Path(here) / d).is_junction()]
            for name in filenames:
                p = Path(here) / name
                if p.suffix.lower() in ARCHIVE_EXT and _is_regular(p):
                    result.append(p)
    else:
        result = [p for p in root.iterdir()
                  if p.suffix.lower() in ARCHIVE_EXT and _is_regular(p)]
    return result


def _name_conflict(parent: Path, candidate: str, source: str) -> bool:
    desired = candidate.casefold()
    return any(p.name.casefold() == desired and p.name != source
               for p in parent.iterdir())


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    new_name: str


def plan_code_only_renames(root: str | Path, results: tuple[Result, ...],
                           *, recursive: bool = True) -> list[RenamePlan]:
    root = _check_root(Path(root))
    scan_counts = Counter(row.query.casefold() for row in results)
    by_name: dict[str, list[Path]] = {}
    for p in _archive_paths(root, recursive):
        by_name.setdefault(p.name.casefold(), []).append(p)
    plans: list[RenamePlan] = []
    for row in results:
        id_pair = bare_id(row.query)
        if not id_pair or row.status != "confirmed" or not row.selected_store:
            continue
        store, code = id_pair
        # A numeric label or one of several products is not enough for renaming.
        if store != row.selected_store or scan_counts[row.query.casefold()] != 1:
            continue
        candidates = [w for w in row.works if w.status == "verified" and
                      w.store == store and str(w.code).upper() == code]
        if len(candidates) != 1 or len(row.works) != 1:
            continue
        work = candidates[0]
        if not _valid_identity(store, code, work.url):
            continue
        matches = by_name.get(row.query.casefold(), [])
        if len(matches) != 1 or matches[0].name != row.query:
            continue
        source = matches[0]
        candidate = official_filename(work.title, store, code, source.suffix)
        if not candidate or candidate.casefold() == source.name.casefold():
            continue
        if _name_conflict(source.parent, candidate, source.name):
            continue
        plans.append(RenamePlan(source, candidate))
    return plans


def _identity(path: Path) -> dict[str, int]:
    if not _is_regular(path):
        raise ValueError("일반 파일이 아니거나 연결된 파일입니다.")
    info = path.stat(follow_symlinks=False)
    return {
        "dev": info.st_dev, "ino": info.st_ino,
        "length": info.st_size, "mtime_ns": info.st_mtime_ns,
    }


def _store_journal(file: Path, document: dict) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=2)
    temp = file.with_name(file.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, file)


def apply_code_only_renames(root: str | Path, results: tuple[Result, ...],
                            *, recursive: bool = True,
                            journal_directory: Path | None = None) -> tuple[int, list[str]]:
    """Automatically rename approved bare-ID files; persist undo BEFORE each move.

    The user opts in before choosing the folder, then approves the folder (Y).
    There is intentionally no second YES prompt.
    """
    root = _check_root(Path(root))
    plans = plan_code_only_renames(root, results, recursive=recursive)
    if not plans:
        return 0, []
    history = Path(journal_directory) if journal_directory else history_dir()
    history.mkdir(parents=True, exist_ok=True)
    filename = JOURNAL_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex + ".json"
    journal_file = history / filename
    journal = {"format": "playdock-auto-rename-v1",
               "root": str(root), "records": [], "undone": False}
    _store_journal(journal_file, journal)
    count = 0
    descriptions: list[str] = []
    for plan in plans:
        source = plan.source
        target = source.with_name(plan.new_name)
        try:
            original = _identity(source)
            if not original["ino"] or _name_conflict(source.parent, target.name, source.name):
                continue
            record = {"relative_dir": str(source.parent.relative_to(root)),
                      "old": source.name, "new": target.name,
                      "identity": original, "state": "pending"}
            journal["records"].append(record)
            _store_journal(journal_file, journal)
            # Windows os.rename refuses an existing target; no overwrite.
            os.rename(source, target)
            record["state"] = "done"
            _store_journal(journal_file, journal)
            count += 1
            descriptions.append(f"{record['old']} → {record['new']}")
        except (OSError, ValueError) as exc:
            descriptions.append(f"[건너뜀] {source.name} ({type(exc).__name__})")
            # Preserve journal even if interrupted after the move.
            if not source.exists() and target.exists():
                break
            if journal["records"] and journal["records"][-1].get("old") == source.name:
                journal["records"][-1]["state"] = "skipped"
                try:
                    _store_journal(journal_file, journal)
                except OSError:
                    break
    return count, descriptions


def undo_last_auto_rename(root: str | Path,
                          *, journal_directory: Path | None = None) -> tuple[int, list[str]]:
    """Undo the last applicable batch, refusing replaced or modified files."""
    root = _check_root(Path(root))
    history = Path(journal_directory) if journal_directory else history_dir()
    if not history.is_dir():
        return 0, ["복구할 자동 이름 변경 기록이 없습니다."]
    for journal_file in sorted(history.glob(JOURNAL_PREFIX + "*.json"), reverse=True):
        try:
            journal = json.loads(journal_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (journal.get("format") != "playdock-auto-rename-v1" or
                journal.get("root") != str(root) or journal.get("undone") or
                not journal.get("records")):
            continue
        restored = 0
        messages: list[str] = []
        for entry in reversed(journal["records"]):
            if entry.get("state") not in ("done", "pending"):
                continue
            rel = entry.get("relative_dir")
            old, new = entry.get("old"), entry.get("new")
            if (not isinstance(rel, str) or
                    not isinstance(old, str) or not isinstance(new, str) or
                    Path(old).name != old or Path(new).name != new or
                    not bare_id(old) or
                    "/" in old or "\\" in old or "/" in new or "\\" in new or
                    Path(rel).is_absolute()):
                messages.append("[보호] 복구 이력이 잘못되어 건너뜁니다.")
                continue
            parent = root / rel
            # Reject traversal, junctions and symlinked parent components.
            try:
                parts = Path(rel).parts
                if any(part in ("..", "") for part in parts):
                    raise ValueError("상대 경로 오류")
                check = root
                for part in parts:
                    check = check / part
                    if check.is_symlink() or check.is_junction():
                        raise ValueError("연결 폴더")
                if not parent.resolve().is_relative_to(root):
                    raise ValueError("루트 외부 복구 금지")
                dest = parent / new
                source = parent / old
                # Only undo the same physical file, in the exact expected state.
                if source.exists() or _identity(dest) != entry.get("identity"):
                    raise ValueError("이름 충돌 또는 원본 파일 교체·변경")
                os.rename(dest, source)
                entry["state"] = "undone"
                _store_journal(journal_file, journal)
                restored += 1
                messages.append(f"{new} → {old}")
            except (OSError, ValueError):
                messages.append(f"[보호] 변경되거나 충돌하는 파일은 복구하지 않음: {new}")
        journal["undone"] = not any(x.get("state") in ("done", "pending")
                                    for x in journal["records"])
        _store_journal(journal_file, journal)
        return restored, messages
    return 0, ["복구할 자동 이름 변경 기록이 없습니다."]
