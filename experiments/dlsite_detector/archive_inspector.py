"""로컬 게임 압축파일의 *목록만* 확인하는 독립 신원 확인 보조 도구.

ZIP/7z/RAR 디렉터리 메타데이터만 읽는다. 압축 해제, 멤버 바이트 읽기,
실행, 인터넷 요청, 사용자 DB 변경은 하지 않는다. 결론은 항상 '단서'이며
게임 이름이나 작품 유형을 확정할 근거로 사용해서는 안 된다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
import re
import zipfile

from .detector import extract_code
from .archive_encryption import EncryptionProbe, probe_archive_encryption


MAX_MEMBERS = 120_000
MAX_REPORTED = 60
MAX_CANDIDATES = 8
MAX_WORK_CODES = 12
GENERIC_EXECUTABLES = frozenset({
    "game", "game.exe", "launcher", "start", "run", "setup", "install",
    "uninstall", "unins000", "unitycrashhandler32", "unitycrashhandler64",
    "rpg_rt", "rpg_rt.exe", "nw", "nw.exe", "renpy", "renpy.exe",
    "electron", "crashreporter", "config", "update", "patch", "client",
    "play", "startgame", "engine", "win64-shipping", "gameassembly",
    "notificationhelper", "notificationhelper.exe", "notification_helper",
    "notification_helper.exe", "editor", "editor.exe", "databasecleanuptool",
    "databasecleanuptool.exe", "common.extprotocol.executor",
    "eztransxp.extprotocol", "lec.extprotocol", "crashhandler",
})
GENERIC_FOLDERS = frozenset({
    "game", "games", "data", "assets", "bin", "binaries", "content",
    "windows", "win64", "patch", "update", "release", "www", "plugins",
    "locales", "swiftshader", "audio", "css", "font", "fonts", "img",
    "image", "images", "icon", "icons", "effects", "export", "resources",
    "save", "saves", "dictionaries", "dataex", "cache", "logs",
    "translations", "tools", "runtime", "package.nw",
})
DISPLAY_EXTENSIONS = (".exe", ".ini", ".json", ".rpa", ".pck", ".pak", ".dll", ".wolf")


@dataclass(frozen=True)
class FileEvidence:
    path: str
    reason: str
    size: int | None = None


@dataclass(frozen=True)
class ArchiveInspection:
    archive_name: str
    format: str
    state: str
    member_count: int
    listed_count: int
    total_uncompressed_bytes: int | None
    encrypted: bool
    engine_hints: tuple[str, ...]
    title_candidates: tuple[str, ...]
    product_codes: tuple[str, ...]
    evidence: tuple[FileEvidence, ...]
    reason: str
    package_signals: tuple[str, ...] = ()
    localization_signals: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_member_path(name: str) -> tuple[str, ...] | None:
    """압축파일 내부의 위험한 절대경로/상위 참조는 단서로 사용하지 않는다."""
    if not isinstance(name, str) or not name or "\x00" in name:
        return None
    normalized = name.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if (parsed.is_absolute() or normalized.startswith(("/", "\\"))
            or any(part == ".." or ":" in part for part in parsed.parts)):
        return None
    parts = tuple(part for part in parsed.parts if part not in ("", "."))
    return parts or None


def _clean_candidate(value: str) -> str:
    """원본 이름에서 조회용 제목 후보만 추출하며 원본을 변경하지 않는다."""
    value = re.sub(r"\.(?:exe|zip|7z|rar)$", "", value, flags=re.I).strip()
    value = re.sub(r"(?<![A-Za-z0-9])(?:RJ|VJ|BJ|EJ)\d{6,8}(?![A-Za-z0-9])",
                   " ", value, flags=re.I)
    value = re.sub(r"\[(?:v\d[^\]]*|ver\.?\s*\d[^\]]*|한국어|한글패치|번역패치|patch|translation)\]",
                   " ", value, flags=re.I)
    value = re.sub(r"[_\s]+", " ", value).strip(" -_.")
    return value[:160]


def _interesting_title(name: str, *, is_folder: bool = False) -> str:
    value = _clean_candidate(name)
    normalized = value.casefold().replace(" ", "").replace("_", "")
    excluded = GENERIC_FOLDERS if is_folder else GENERIC_EXECUTABLES
    if (not 3 <= len(value) <= 160 or not any(ch.isalpha() for ch in value)
            or normalized in excluded
            or value.casefold().endswith((".dll", ".pck", ".pak", ".exe", ".json"))):
        return ""
    return value


HELPER_DIRS = frozenset({
    "bepinex", "plugins", "xunity.autotranslator", "translators",
    "fullnet", "tools", "support", "redist", "redistributables",
})


def _is_helper_executable(parts: tuple[str, ...]) -> bool:
    lowered = [v.casefold() for v in parts]
    name = lowered[-1]
    stem = Path(name).stem.replace("_", "").replace("-", "").replace(".", "")
    if (stem in {"notificationhelper", "databasecleanuptool", "crashreporter",
                 "unitycrashhandler32", "unitycrashhandler64", "editor",
                 "eztransxpextprotocol", "lecextprotocol",
                 "commonextprotocolexecutor"}):
        return True
    return any(part in HELPER_DIRS for part in lowered[:-1])


def _list_archive(path: Path, suffix: str):
    """목록/크기/암호 표시만 반환. extract/open/read(member)는 호출하지 않는다."""
    if suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for item in zf.infolist():
                yield item.filename, int(item.file_size), item.is_dir(), bool(item.flag_bits & 1) or item.compress_type == 99
    elif suffix == ".7z":
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError("7z 파일 목록 확인에는 py7zr가 필요합니다.") from exc
        with py7zr.SevenZipFile(path, mode="r") as zf:
            encrypted = bool(zf.needs_password())
            for item in zf.list():
                yield (item.filename, int(getattr(item, "uncompressed", 0) or 0),
                       bool(getattr(item, "is_directory", False)), encrypted)
    elif suffix == ".rar":
        try:
            import rarfile
        except ImportError as exc:
            raise RuntimeError("RAR 파일 목록 확인에는 rarfile이 필요합니다.") from exc
        with rarfile.RarFile(path) as rf:
            encrypted = bool(rf.needs_password())
            for item in rf.infolist():
                yield item.filename, int(item.file_size), bool(item.isdir()), encrypted
    else:
        raise ValueError("지원하지 않는 파일 형식입니다.")


def inspect_archive(
    path: Path, *, encryption_probe: EncryptionProbe | None = None,
) -> ArchiveInspection:
    """파일 목록만 분석해 정체 검색에 사용할 *후보*를 반환한다.

    리스트를 DB에 저장하거나 외부 사이트로 전송하지 않는다.
    Password-encrypted header는 읽을 수 없는 상태로 처리한다.
    """
    archive = Path(path)
    suffix = archive.suffix.lower()
    fmt = suffix.removeprefix(".")
    if suffix not in (".zip", ".7z", ".rar"):
        return ArchiveInspection(archive.name, fmt, "unsupported", 0, 0, None,
                                 False, (), (), (), (), "지원하지 않는 압축파일 형식입니다.")
    if not archive.is_file() or archive.is_symlink():
        return ArchiveInspection(archive.name, fmt, "unavailable", 0, 0, None,
                                 False, (), (), (), (), "파일을 읽을 수 없거나 링크 파일입니다.")

    # 암호 보호 압축파일은 파일명이 보이는 형식이라도 내부 폴더명/EXE
    # 이름/작품 코드를 정체 판단에 사용하지 않는다.
    probe = encryption_probe if encryption_probe is not None else probe_archive_encryption(archive)
    if probe.state != "clear":
        encrypted = probe.state == "encrypted"
        return ArchiveInspection(
            archive.name, fmt,
            "encrypted" if encrypted else "unavailable",
            0, 0, None, encrypted, (), (), (), (),
            ("암호화된 압축파일은 내부 목록 단서를 분석하지 않습니다. "
             if encrypted else "암호 상태가 불명확해 내부 분석을 생략했습니다. ")
            + probe.reason,
        )

    total = 0
    count = 0
    listed = 0
    invalid = 0
    encrypted = False
    truncated = False
    evidence: list[FileEvidence] = []
    titles: dict[str, int] = {}
    codes: list[str] = []
    engines: set[str] = set()
    package: set[str] = set()
    localization: set[str] = set()
    seen_paths: set[str] = set()

    try:
        for filename, size, is_dir, protected in _list_archive(archive, suffix):
            count += 1
            if count > MAX_MEMBERS:
                truncated = True
                break
            encrypted = encrypted or protected
            total += max(0, size)
            parts = _safe_member_path(filename)
            if not parts:
                invalid += 1
                continue
            listed += 1
            joined = "/".join(parts)
            lowered = joined.casefold()
            basename = parts[-1]
            if lowered in seen_paths:
                continue
            seen_paths.add(lowered)

            code = extract_code(joined)
            if code and code not in codes and len(codes) < MAX_WORK_CODES:
                codes.append(code)
                if len(evidence) < MAX_REPORTED:
                    evidence.append(FileEvidence(joined, "작품 코드 형식의 문자열 발견", size))

            if len(parts) > 1 and len(titles) < 64:
                root_title = _interesting_title(parts[0], is_folder=True)
                if root_title:
                    titles[root_title] = max(titles.get(root_title, 0), 1)

            if is_dir:
                continue
            stem, extension = Path(basename).stem, Path(basename).suffix.casefold()
            if extension == ".exe":
                if (basename.casefold() not in {"uninstall.exe", "setup.exe", "unins000.exe"}
                        and not _is_helper_executable(parts)):
                    package.add("Windows 실행파일 존재")
            if extension == ".rpa":
                package.add("Ren'Py 게임 데이터 파일 존재")
            if extension in {".rgssad", ".rgss2a", ".rgss3a"}:
                package.add("RPG Maker 게임 데이터 파일 존재")
            if extension == ".pck":
                package.add("Godot 게임 데이터 파일 후보")
            if basename.casefold() in {"package.nw", "app.asar"}:
                package.add("NW.js/Electron 패키지 데이터 존재")
            if lowered.endswith(("/www/js/rpg_managers.js", "/js/rpg_managers.js")):
                package.add("RPG Maker MV/MZ 게임 데이터 존재")
            if "/tl/korean/" in "/" + lowered or re.search(
                    r"(?:^|/)(?:korean|ko-kr|ko_kr|한국어)(?:/|$)", lowered):
                localization.add("한국어 번역 파일/폴더 경로 단서")
            if extension == ".exe":
                exe_title = "" if _is_helper_executable(parts) else _interesting_title(stem)
                if exe_title and len(titles) < 64:
                    titles[exe_title] = max(titles.get(exe_title, 0), 3)
                    if len(evidence) < MAX_REPORTED:
                        evidence.append(FileEvidence(joined, "게임 제목 후보가 될 수 있는 EXE 이름", size))
            # 엔진 정보는 게임의 정체와 다르므로 별도 단서로만 보관한다.
            engine = None
            if re.search(r"[^/]+_data/", lowered) or basename.casefold() in ("unityplayer.dll", "gameassembly.dll"):
                engine = "Unity"
            elif "/renpy/" in "/" + lowered or extension == ".rpa":
                engine = "Ren'Py"
            elif basename.casefold() in ("rpg_rt.ini", "rpg_rt.exe", "game.rgss3a", "game.rgss2a", "game.rgssad"):
                engine = "RPG Maker"
            elif extension == ".pck":
                engine = "Godot (추정)"
            elif extension == ".pak" and ("/content/paks/" in "/" + lowered or "windowsnoeditor" in lowered):
                engine = "Unreal Engine (추정)"
            elif basename.casefold() == "package.nw":
                engine = "NW.js (추정)"
            elif basename.casefold() == "app.asar":
                engine = "Electron (추정)"
            elif lowered.endswith(("/www/js/rpg_managers.js", "/js/rpg_managers.js")):
                engine = "RPG Maker MV/MZ (추정)"
            if engine:
                engines.add(engine)
                if len(evidence) < MAX_REPORTED:
                    evidence.append(FileEvidence(joined, f"게임 엔진 단서: {engine}", size))
    except Exception as exc:
        reason = "압축파일 목록을 읽지 못했습니다."
        if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
            reason = "압축파일 헤더가 암호화되어 파일 목록을 볼 수 없습니다."
        return ArchiveInspection(archive.name, fmt, "needs_password" if reason.startswith("압축파일 헤더") else "unavailable",
                                 count, listed, total or None, encrypted or "암호화" in reason,
                                 tuple(sorted(engines)), (), tuple(codes), tuple(evidence),
                                 reason + f" ({type(exc).__name__})")

    state = "limit_exceeded" if truncated else ("partial" if invalid else "ok")
    note = "파일 목록 메타데이터만 확인했습니다. 게임 정체는 확정하지 않았습니다."
    if truncated:
        note += " 항목 제한을 넘어 목록 분석을 중단했습니다."
    if invalid:
        note += f" 위험하거나 잘못된 내부 경로 {invalid}개는 무시했습니다."
    if encrypted:
        note += " 암호 보호된 내용은 읽지 않았습니다."
    ordered_titles = sorted(titles, key=lambda title: (-titles[title], title.casefold()))
    return ArchiveInspection(
        archive.name, fmt, state, count, listed, total, encrypted,
        tuple(sorted(engines)), tuple(ordered_titles[:MAX_CANDIDATES]),
        tuple(codes), tuple(evidence), note,
        tuple(sorted(package)), tuple(sorted(localization)),
    )
