"""선택적 내부 메타데이터 검사: 비암호화 압축 안의 작은 설정 파일만 읽는다.

실행/디스크 추출/사용자 DB 변경은 하지 않는다. 파일 종류별 파서가
명시적으로 지정한 필드만 단서로 수집하고 제목/품번/제작사/프로젝트명을
분리해 근거 출처 및 등급을 함께 보존한다. 게임 정체는 확정하지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import stat
import zipfile

from .archive_inspector import _safe_member_path
from .detector import extract_code
from .archive_encryption import probe_archive_encryption
from .search_terms import cleaned_search_title
from .metadata_fields import parse_metadata_fields


MAX_MEMBERS = 20_000
MAX_CANDIDATE_FILES = 8
MAX_MEMBER_BYTES = 32_768
MAX_TOTAL_BYTES = 131_072
MAX_COMPRESSED_BYTES = 131_072
MAX_RATIO = 120
MAX_TITLES = 6
MAX_CODES = 4
MAX_STEAM_IDS = 4
MAX_EVIDENCE = 24

ALLOWED_EXACT = frozenset({
    "readme", "readme.txt", "readme.md",
    "game.ini", "rpg_rt.ini", "project.godot",
    "game.json", "metadata.json", "package.json", "version.json",
    "system.json", "steam_appid.txt",
    "app.info", "options.rpy",
})
ALLOWED_SUFFIX = re.compile(r"^readme(?:[_\-][a-z]{2,3})?\.(?:txt|md)$", re.I)
READABLE = frozenset({".txt", ".md", ".ini", ".json", ".godot", ".info", ".rpy"})
TITLE_KEY = re.compile(
    r"(?i)^\s*(?:game_?title|game_?name|title|display_?name|product_?name"
    r"|config/name|config\.name|work_?name|作品名|게임명|게임제목)\s*[:=]\s*(.+?)\s*$"
)
README_TITLE = re.compile(
    r"(?i)^\s*(?:게임명|게임 제목|작품명|game\s*title|game\s*name"
    r"|title|作品名|ゲームタイトル)\s*[:：=]\s*(.+?)\s*$"
)
CODE_KEY = re.compile(
    r"(?i)^\s*(?:dlsite_?(?:code|id)?|work_?(?:no|id)|product_?id|품번)"
    r"\s*[:：=]\s*((?:RJ|VJ|BJ|EJ)\d{6,8})\s*$"
)
RENPY_TITLE = re.compile(
    r"(?i)^\s*define\s+config\.name\s*=\s*(?:_\s*\(\s*)?(['\"])(.{2,140}?)\1"
)
CODE_RE = re.compile(r"(?<![A-Za-z0-9])(?:RJ|VJ|BJ|EJ)\d{6,8}(?![A-Za-z0-9])", re.I)
SENSITIVE = re.compile(r"(?i)(?:https?://|(?:[A-Z]:[\\/])|[\\/]{2}|@|password|passwd|token|secret|api[_-]?key|bearer)")
GENERIC_TITLES = frozenset({"game", "new game", "untitled", "project", "readme", "nwjs", "electron", "unity"})


@dataclass(frozen=True)
class MetadataEvidence:
    member: str
    field: str
    candidate_title: str  # 호환 필드: 작품 코드·제작사라면 해당 값을 보관
    kind: str = "title"
    strength: str = "supporting"
    parser: str = "generic"


@dataclass(frozen=True)
class MetadataInspection:
    archive_name: str
    state: str
    inspected_files: int
    read_bytes: int
    title_candidates: tuple[str, ...]
    product_codes: tuple[str, ...]
    evidence: tuple[MetadataEvidence, ...]
    reason: str
    steam_app_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def strong_titles(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            e.candidate_title for e in self.evidence
            if e.kind == "title" and e.strength == "strong"
        ))


def _safe_title(value) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip().strip("'\"").strip().replace("\\n", " ")
    if len(name) < 3 or len(name) > 140 or SENSITIVE.search(name):
        return ""
    if any(ord(c) < 32 for c in name):
        return ""
    if name.casefold() in GENERIC_TITLES:
        return ""
    # 검색어가 상대 경로/수치/링크가 아니고 의미 있는 글자를 포함하는지 검사.
    if re.fullmatch(r"[\d.\-_: ]+", name) or name.startswith((".", "/", "\\")):
        return ""
    name = cleaned_search_title(name)
    if len(name) < 3 or not any(c.isalpha() for c in name):
        return ""
    # 확장자/경로 형태나 실행 인수는 제목으로 사용하지 않는다.
    if any(c in name for c in ("/", "\\", "<", ">", "|", "\x00")):
        return ""
    return name[:120]


def _pick_members(rows) -> list[tuple[str, str]]:
    candidates = []
    for member, size, compressed, encrypted, is_dir, symlink in rows[:MAX_MEMBERS]:
        if is_dir or encrypted or symlink or size <= 0 or size > MAX_MEMBER_BYTES:
            continue
        if compressed is not None and (compressed <= 0 or compressed > MAX_COMPRESSED_BYTES
                                       or size / compressed > MAX_RATIO):
            continue
        parts = _safe_member_path(member)
        if parts is None or len(parts) > 5:
            continue
        basename = parts[-1].casefold()
        if (basename not in ALLOWED_EXACT and not ALLOWED_SUFFIX.fullmatch(basename)):
            continue
        if basename == "system.json" and not "/".join(p.casefold() for p in parts).endswith("/data/system.json"):
            continue
        if Path(basename).suffix.casefold() not in READABLE and basename not in ("readme", "steam_appid.txt"):
            continue
        candidates.append((member, basename))
    # 게임 실행 설정과 엔진별 title 필드를 패키지/README보다 우선 확인한다.
    order = {
        "steam_appid.txt": 0, "game.ini": 0, "rpg_rt.ini": 0, "options.rpy": 0,
        "system.json": 0,
        "app.info": 1, "project.godot": 1, "game.json": 2,
        "metadata.json": 3, "package.json": 4, "version.json": 5,
    }
    candidates.sort(key=lambda x: (
        order.get(x[1], 9), len(x[0].split("/")), x[0].casefold(),
    ))
    return candidates[:MAX_CANDIDATE_FILES]


def _parse_metadata_text(member: str, payload: bytes):
    """엔진별 허용된 필드만 추출한다 (전체 텍스트 검색 아님)."""
    return parse_metadata_fields(member, payload)


def _accept_evidence(member: str, payload: bytes,
                     titles: list[str], codes: list[str],
                     evidence: list[MetadataEvidence],
                     steam_ids: list[str]) -> None:
    """필드 등급과 출처를 유지하며 제목과 다른 종류의 단서를 혼동하지 않는다."""
    for item in _parse_metadata_text(member, payload):
        if item.kind == "steam_app_id":
            steam_id = item.value.strip()
            if not (steam_id.isascii() and steam_id.isdecimal()
                    and 3 <= len(steam_id) <= 10):
                continue
            if steam_id not in steam_ids and len(steam_ids) < MAX_STEAM_IDS:
                steam_ids.append(steam_id)
            if len(evidence) < MAX_EVIDENCE:
                evidence.append(MetadataEvidence(
                    member, item.field, steam_id, item.kind, item.strength,
                    item.parser))
            continue
        if item.kind == "product_code":
            code = extract_code(item.value)
            if not code or code.upper() != item.value.upper():
                continue
            if code not in codes and len(codes) < MAX_CODES:
                codes.append(code)
            if len(evidence) < MAX_EVIDENCE:
                evidence.append(MetadataEvidence(
                    member, item.field, code, "product_code", item.strength, item.parser))
            continue
        value = _safe_title(item.value)
        if not value:
            continue
        if item.kind == "title" and value not in titles and len(titles) < MAX_TITLES:
            titles.append(value)
        # 중복 제목이라도 서로 다른 *파일*의 근거는 기록한다.
        if len(evidence) < MAX_EVIDENCE:
            evidence.append(MetadataEvidence(
                member, item.field, value, item.kind, item.strength, item.parser))


def _zip_index(path: Path):
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist()[:MAX_MEMBERS]:
            mode = (info.external_attr >> 16) & 0o170000
            yield (info.filename, info.file_size, info.compress_size,
                   bool(info.flag_bits & 1) or info.compress_type == 99,
                   info.is_dir(), mode == stat.S_IFLNK)


def _rar_index(path: Path):
    import rarfile
    with rarfile.RarFile(path) as archive:
        for info in archive.infolist()[:MAX_MEMBERS]:
            solid = bool(info.flags & getattr(rarfile, "RAR_FILE_SOLID", 0))
            yield (info.filename, info.file_size, info.compress_size,
                   bool(info.needs_password()) or solid, info.isdir(), False)



def _inspect_non_solid_7z(archive: Path) -> MetadataInspection:
    """py7zr >= 1.1.4 해제 상한을 사용하여 비-solid 소형 항목만 메모리에서 읽기."""
    try:
        import py7zr
        from importlib.metadata import version
        from io import BytesIO
        ver = tuple(int(part) for part in version("py7zr").split(".")[:3])
        if ver < (1, 1, 4):
            raise RuntimeError("보안 상한을 지원하는 py7zr 1.1.4 이상이 필요")
    except (ImportError, ValueError, RuntimeError) as exc:
        return MetadataInspection(archive.name, "index_only", 0, 0, (), (), (),
                                  f"7z 내용 분석 생략: {type(exc).__name__}")

    class BoundedMemory(py7zr.Py7zIO):
        def __init__(self):
            self.output = BytesIO()
        def write(self, chunk):
            if self.output.tell() + len(chunk) > MAX_MEMBER_BYTES:
                raise ValueError("7z 멤버 읽기 한도 초과")
            return self.output.write(chunk)
        def read(self, size=None):
            return self.output.read(size)
        def seek(self, offset, whence=0):
            return self.output.seek(offset, whence)
        def flush(self):
            return None
        def size(self):
            return self.output.getbuffer().nbytes

    class MemoryFactory(py7zr.WriterFactory):
        def __init__(self):
            self.members = {}
        def create(self, name):
            writer = BoundedMemory()
            self.members[name] = writer
            return writer

    try:
        with py7zr.SevenZipFile(archive, mode="r", max_extract_size=MAX_TOTAL_BYTES) as zf:
            if zf.needs_password():
                return MetadataInspection(archive.name, "index_only", 0, 0, (), (), (),
                                          "암호화된 7z는 목록 단서만 확인")
            if zf.archiveinfo().solid:
                return MetadataInspection(archive.name, "index_only", 0, 0, (), (), (),
                                          "7z 솔리드 압축은 대용량 블록 해제 위험으로 내용 읽기 생략")
            files = zf.list()[:MAX_MEMBERS]
            rows = [(item.filename, int(item.uncompressed or 0),
                     int(item.compressed) if item.compressed is not None else None,
                     False, bool(item.is_directory), bool(item.is_symlink))
                    for item in files]
            selected = _pick_members(rows)
            if not selected:
                return MetadataInspection(archive.name, "no_metadata", 0, 0, (), (), (),
                                          "제한된 메타데이터 후보 파일 없음")
            factory = MemoryFactory()
            zf.extract(targets=[p for p, _ in selected], recursive=False, factory=factory)
            titles, codes, evidence, steam_ids = [], [], [], []
            size = 0
            for member, basename in selected:
                writer = factory.members.get(member)
                if writer is None:
                    continue
                contents = writer.output.getvalue()
                size += len(contents)
                if size > MAX_TOTAL_BYTES:
                    return MetadataInspection(archive.name, "index_only", 0, 0, (), (), (),
                                              "7z 누적 읽기 제한 초과")
                _accept_evidence(member, contents, titles, codes, evidence, steam_ids)
            return MetadataInspection(
                archive.name, "ok" if titles or codes or steam_ids else "no_metadata",
                len(factory.members), size, tuple(titles), tuple(codes),
                tuple(evidence), "안전 상한을 적용한 비-solid 7z 소형 항목만 조회",
                tuple(steam_ids),
            )
    except Exception as exc:
        return MetadataInspection(archive.name, "index_only", 0, 0, (), (), (),
                                  f"7z 부분 읽기를 완료하지 못해 목록 정보만 사용: {type(exc).__name__}")


def inspect_metadata(path: Path) -> MetadataInspection:
    """비암호화 압축 안의 작은 파일만 메모리에 읽고 제목·코드 근거를 남긴다.

    RAR은 추가 백엔드가 필요할 수 있고, 솔리드 7z와 암호 압축은 읽지 않는다.
    """
    archive = Path(path)
    if archive.is_symlink() or not archive.is_file():
        return MetadataInspection(archive.name, "unavailable", 0, 0, (), (), (),
                                  "일반 로컬 압축파일이 아닙니다.")
    # --metadata를 명시해도 암호화된 압축파일의 내용은 절대 읽지 않는다.
    probe = probe_archive_encryption(archive)
    if probe.state != "clear":
        return MetadataInspection(
            archive.name, "encrypted" if probe.is_encrypted else "unavailable",
            0, 0, (), (), (),
            ("암호화된 파일은 내부 메타데이터를 읽지 않습니다. " if probe.is_encrypted
             else "암호 상태가 불명확해 메타데이터 검사를 생략했습니다. ")
            + probe.reason,
        )
    suffix = archive.suffix.lower()
    if suffix == ".7z":
        return _inspect_non_solid_7z(archive)
    if suffix not in {".zip", ".rar"}:
        return MetadataInspection(archive.name, "unsupported", 0, 0, (), (), (),
                                  "선택적 메타데이터 읽기 미지원 형식입니다.")

    titles = []
    codes = []
    steam_ids = []
    evidence = []
    read_bytes = 0
    count = 0
    errors = []
    try:
        import contextlib
        if suffix == ".zip":
            reader = zipfile.ZipFile(archive)
        else:
            import rarfile
            reader = rarfile.RarFile(archive)
        with reader as zf:
            if suffix == ".zip":
                infos = zf.infolist()[:MAX_MEMBERS]
                rows = [
                    (item.filename, item.file_size, item.compress_size,
                     bool(item.flag_bits & 1) or item.compress_type == 99,
                     item.is_dir(), (item.external_attr >> 16) & 0o170000 == stat.S_IFLNK)
                    for item in infos
                ]
            else:
                import rarfile
                infos = zf.infolist()[:MAX_MEMBERS]
                rows = [
                    (item.filename, item.file_size, item.compress_size,
                     bool(item.needs_password())
                     or bool(item.flags & getattr(rarfile, "RAR_FILE_SOLID", 0)),
                     item.isdir(), False)
                    for item in infos
                ]
            for member, basename in _pick_members(rows):
                if read_bytes >= MAX_TOTAL_BYTES:
                    break
                try:
                    with zf.open(member, "r") as stream:
                        cap = min(MAX_MEMBER_BYTES, MAX_TOTAL_BYTES - read_bytes)
                        chunk = stream.read(cap + 1)
                except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, EOFError) as exc:
                    errors.append(type(exc).__name__)
                    continue
                count += 1
                read_bytes += len(chunk)
                if len(chunk) > cap:
                    continue
                _accept_evidence(member, chunk, titles, codes, evidence, steam_ids)
    except (ImportError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        errors.append(type(exc).__name__)

    if titles or codes or steam_ids:
        state = "ok"
    elif errors:
        state = "partial"
    else:
        state = "no_metadata"
    return MetadataInspection(
        archive.name, state, count, read_bytes,
        tuple(titles), tuple(codes), tuple(evidence),
        ("제한된 메타데이터 제목 필드만 추출했습니다. "
         "로컬 게임과의 동일성은 증명하지 않습니다."
         + (" 일부 파일 읽기 실패: " + ", ".join(errors[:3]) if errors else "")),
        tuple(steam_ids),
    )
