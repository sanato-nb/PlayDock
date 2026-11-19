"""v0.10 독립 게임 정체 탐색: 이름과 선택적 상품번호만 사용.

압축 이름, 최상위 폴더, 주요 실행파일의 *이름*, README의 명시 라벨만 수집한다.
엔진, 게임 버전, 언어/번역 여부, 파일 크기, 게임 데이터 내용은 판정에 쓰지 않는다.
게임 EXE를 실행/해제/읽지 않으며 외부에는 선별된 이름/식별자 검색어만 보낸다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import time
from typing import Callable

from .archive_encryption import probe_archive_encryption
from .archive_inspector import (
    _list_archive, _safe_member_path, _interesting_title,
    _is_helper_executable,
)
from .catalog_aliases import DISTRIBUTION_PREFIX, explicit_title_keys
from .detector import normalized_title
from .identity_hints import extract_hints, DL_CODE, STEAM_ID
from .internal_metadata import inspect_readme_metadata
from .pipeline import SearchDecision
from .search_terms import cleaned_search_title

MAX_MEMBERS = 120_000
MAX_SEARCHES_FAST = 3
MAX_SEARCHES_DETAILED = 6
MAX_VISIBLE_CLUES = 30
# 접두사만 그럴듯한 게임 이름처럼 보이는 폴더/실행 파일 제외.
FOLDER_NOISE = re.compile(
    r"(?i)^(?:cg(?:[\s_-]|$)|save(?:s|[\s_-]files?)?(?:[\s_-]|$)|"
    r"bepinex|monobleedingedge|engine|python|renpy|game[\s_-]?overrides|"
    r"bonus|extras?|artbook|manual|readme|support|tools?|resources?|"
    r"runtime|plugins?|locales?|translations?|game[\s_-]?(?:kr|eng|en|jp)|"
    r"win64|binaries|data|content|asset(?:s)?)(?:[\s_-]|$)"
)
EXEC_NOISE = re.compile(
    r"(?i)^(?:game[\s_-]?(?:kr|eng|en|jp)|createdump|pythonw?|zsync|"
    r"crashreportclient|unrealcefsubprocess|unitycrashhandler\d*|"
    r"opensavefolder|resetconfig|uninstaller|unins\d*|"
    r"launcher|config|configuration|settings?|update|updater|"
    r"installer|setup|rpg_rt|nw|player|run|start|"
    r"reportcrash|errorreporter|gameassembly|notification[_ -]?helper)$"
)
SUPPORT_DIRS = frozenset({
    "engine", "bepinex", "lib", "mono", "monobleedingedge", "runtime",
    "thirdparty", "redist", "redistributables", "tools", "support",
    "dependencies", "python", "plugins", "renpy",
})


@dataclass(frozen=True)
class NameCodeClue:
    kind: str  # title / product_code
    value: str
    source: str  # archive_name / root_folder / main_exe / readme
    detail: str = ""


@dataclass(frozen=True)
class SimpleScan:
    archive_name: str
    encryption_state: str
    scan_state: str
    scanned_entries: int
    clues: tuple[NameCodeClue, ...]
    exe_candidates: tuple[str, ...]
    exe_ambiguous: bool
    readme_state: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimpleAttempt:
    query: str
    basis: str
    decision: SearchDecision

    def to_dict(self) -> dict:
        return {
            "query": self.query, "basis": self.basis,
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True)
class SimpleResult:
    archive_name: str
    status: str  # identified / likely / multiple / unidentified / search_error
    title: str
    product_code: str
    reason: str
    scan: SimpleScan
    attempts: tuple[SimpleAttempt, ...]
    alternatives: tuple[str, ...]
    search_queries: tuple[str, ...]
    notes: tuple[str, ...]
    elapsed_seconds: float

    @property
    def is_unresolved(self) -> bool:
        return self.status != "identified"

    @property
    def label(self) -> str:
        return {
            "identified": "공식 작품 식별",
            "likely": "유력 후보 · 확인 필요",
            "multiple": "복수 후보 · 보류",
            "unidentified": "정체 미확인",
            "search_error": "검색 실패 · 재검사",
        }[self.status]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["label"] = self.label
        data["is_unresolved"] = self.is_unresolved
        data["scan"] = self.scan.to_dict()
        data["attempts"] = [a.to_dict() for a in self.attempts]
        data["post_identity_checks"] = "deferred"
        data["local_file_identity_cryptographically_verified"] = False
        return data


def _codes(raw: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x.upper() for x in DL_CODE.findall(raw or "")))[:6]


def _candidate_title(raw: str, *, folder: bool = False) -> str:
    title = _interesting_title(raw, is_folder=folder)
    title = cleaned_search_title(title)
    if not title:
        return ""
    if folder and FOLDER_NOISE.match(title):
        return ""
    if not folder and EXEC_NOISE.fullmatch(title):
        return ""
    if not any(ch.isalpha() for ch in title):
        return ""
    return title[:150]


def _key(raw: str) -> str:
    # 배포물(번역 패치 등)의 상품명 표기를 제거하는 것은 정확한 이름
    # 대조만을 위한 것이며 배포물 관계를 자동 확정하는 작업이 아니다.
    base = DISTRIBUTION_PREFIX.sub("", raw).strip()
    return normalized_title(base)


def _readme_clues(path: Path, probe, append, notes: list[str]) -> str:
    metadata = inspect_readme_metadata(path, encryption_probe=probe)
    if metadata.state in {"index_only", "partial", "unavailable"}:
        notes.append("README 미검사/일부 검사: " + metadata.state)
    for title in metadata.title_candidates:
        cleaned = _candidate_title(title)
        if cleaned:
            append("title", cleaned, "readme", "명시된 게임명 라벨")
    for code in metadata.product_codes:
        for value in _codes(code):
            append("product_code", value, "readme", "명시된 상품번호 라벨")
    for sid in metadata.steam_app_ids:
        if re.fullmatch(r"\d{3,10}", sid):
            append("product_code", "Steam App ID: " + sid, "readme",
                   "명시된 공식 플랫폼 식별자")
    return metadata.state


def collect_identity_clues(path: Path) -> SimpleScan:
    """파일 목록(이름) + README 제한 필드만 사용. 어떤 EXE도 실행하지 않음."""
    path = Path(path)
    if (not path.is_file() or path.is_symlink()
            or path.suffix.lower() not in {".zip", ".7z", ".rar"}):
        return SimpleScan(path.name, "unknown", "invalid", 0, (), (), False,
                          "not_inspected", ("지원하지 않는 일반 압축파일입니다.",))
    clues: list[NameCodeClue] = []
    seen_clues: set[tuple[str, str, str]] = set()
    notes: list[str] = []

    def add(kind: str, value: str, source: str, detail: str = "") -> None:
        if not value or len(value) > 180:
            return
        k = (kind, value.casefold(), source)
        if k not in seen_clues and len(clues) < MAX_VISIBLE_CLUES:
            seen_clues.add(k)
            clues.append(NameCodeClue(kind, value, source, detail))

    archive_title = cleaned_search_title(path.name)
    if archive_title and any(x.isalpha() for x in archive_title):
        add("title", archive_title, "archive_name")
    for code in _codes(path.name):
        add("product_code", code, "archive_name")
    for sid in STEAM_ID.findall(path.stem):
        add("product_code", "Steam App ID: " + sid, "archive_name")

    probe = probe_archive_encryption(path)
    if probe.state != "clear":
        notes.append("암호 상태 때문에 내부 이름과 README를 확인하지 않았습니다.")
        return SimpleScan(path.name, probe.state, "filename_only", 0,
                          tuple(clues), (), False, "not_inspected", tuple(notes))

    folders: dict[str, str] = {}
    exes: list[tuple[tuple[str, ...], str]] = []
    data_dirs: set[str] = set()
    inspected = 0
    scan_state = "ok"
    try:
        for member, _, is_dir, protected in _list_archive(path, path.suffix.lower()):
            inspected += 1
            if inspected > MAX_MEMBERS:
                scan_state = "limit_exceeded"
                notes.append("내부 파일 목록 안전 제한에 도달했습니다.")
                break
            parts = _safe_member_path(member)
            if not parts or protected:
                continue
            if len(parts) > 1:
                for i, part in enumerate(parts[:-1] if not is_dir else parts):
                    if part.lower().endswith("_data"):
                        data_dirs.add("/".join(parts[:i+1]).casefold())
            if parts[0].casefold().endswith("_data"):
                data_dirs.add(parts[0].casefold())
            # 최상위 폴더 한두 단계만 게임 이름 후보로 사용.
            if len(parts) > 1:
                for depth in range(min(2, len(parts)-1)):
                    p = parts[depth]
                    if p not in folders:
                        folders[p] = "/".join(parts[:depth+1])
            if is_dir:
                for depth in range(min(2, len(parts))):
                    p = parts[depth]
                    if p not in folders:
                        folders[p] = "/".join(parts[:depth+1])
                continue
            if parts[-1].lower().endswith(".exe"):
                exes.append((parts, member))
            # 깊은 경로의 RJ 번호는 임의 설정/메모일 가능성이 커서
            # 정체 식별 번호를 자동 추출하지 않는다. 폴더/EXE만 확인.
    except Exception as exc:
        scan_state = "unavailable" if inspected == 0 else "partial"
        notes.append("내부 이름 목록 읽기 실패: " + type(exc).__name__)

    if scan_state in {"ok", "limit_exceeded", "partial"}:
        for name, location in list(folders.items())[:40]:
            title = _candidate_title(name, folder=True)
            if title:
                add("title", title, "root_folder", location)
            if not FOLDER_NOISE.match(name):
                for code in _codes(name):
                    add("product_code", code, "root_folder", location)

    possible: list[tuple[str, str, int]] = []
    for parts, member in exes:
        stem = Path(parts[-1]).stem
        cleaned_stem = re.sub(r"(?i)[-_]win64[-_]shipping$", "", stem)
        title = _candidate_title(cleaned_stem)
        if not title or EXEC_NOISE.match(title) or _is_helper_executable(parts):
            continue
        if any(p.casefold() in SUPPORT_DIRS for p in parts[:-1]):
            continue
        # 높은 점수라도 공식 작품 확인의 증거는 아닌 파일명 추정.
        parent = "/".join(parts[:-1]).casefold()
        same_data_dir = ((parent + "/" if parent else "")
                         + stem.casefold() + "_data") in data_dirs
        score = 1
        if same_data_dir:
            score += 3
        if _key(title) == _key(archive_title) and archive_title:
            score += 2
        if len(parts) > 3:
            score -= 2
        if len(parts) > 2 and "binaries" not in (p.lower() for p in parts):
            score -= 1
        if re.search(r"(?i)[-_]win64[-_]shipping$", stem):
            score = min(score, 2)
        if score >= 1:
            possible.append((title, member, score))

    unique_exes: dict[str, tuple[str, str, int]] = {}
    for entry in possible:
        key = _key(entry[0])
        if key and (key not in unique_exes or entry[2] > unique_exes[key][2]):
            unique_exes[key] = entry
    selected = sorted(unique_exes.values(), key=lambda row: (-row[2], row[0].casefold()))
    ambiguous = len(selected) > 1
    if ambiguous:
        notes.append("서로 다른 주요 EXE 후보가 여러 개입니다. 실행파일 이름은 "
                     "게임명 검색 근거로 자동 선택하지 않았습니다.")
    elif selected:
        title, location, _ = selected[0]
        add("title", title, "main_exe", location)
        for code in _codes(Path(location).stem):
            add("product_code", code, "main_exe", location)

    if len(clues) >= MAX_VISIBLE_CLUES:
        notes.append("이름/품번 근거 표시 개수 제한에 도달했습니다.")
    readme_state = "not_inspected"
    if scan_state != "unavailable":
        readme_state = _readme_clues(path, probe, add, notes)
    return SimpleScan(path.name, probe.state, scan_state, inspected,
                      tuple(clues), tuple(e[0] for e in selected[:12]),
                      ambiguous, readme_state, tuple(notes))


def _queries(scan: SimpleScan, max_queries: int) -> tuple[tuple[str, str], ...]:
    """수집 종료 뒤 검색계획 수립. 이름과 품번 외 정보는 전송하지 않음."""
    clue_rows = list(scan.clues)
    # 파일명 제목은 필수 검색, 코드 역시 존재하면 우선 조회한다.
    order = {
        ("title", "archive_name"): 0,
        ("product_code", "archive_name"): 1,
        ("title", "readme"): 2,
        ("product_code", "readme"): 3,
        ("product_code", "root_folder"): 4,
        ("product_code", "main_exe"): 5,
        ("title", "root_folder"): 6,
        ("title", "main_exe"): 7,
    }
    clue_rows.sort(key=lambda r: order.get((r.kind, r.source), 20))
    unique: set[str] = set()
    result: list[tuple[str, str]] = []
    for clue in clue_rows:
        q = clue.value
        key = " ".join(q.casefold().split())
        if key in unique:
            continue
        unique.add(key)
        result.append((q, clue.source + "/" + clue.kind))
        if len(result) >= max(1, min(8, max_queries)):
            break
    return tuple(result)


def _name_matches(local: str, external: str) -> bool:
    if not local or not external:
        return False
    source = _key(local)
    if not source or len(source) < 3:
        return False
    return source in explicit_title_keys(external) or (
        source == _key(external)
    )


def _match_any_title(scan: SimpleScan, external: str) -> bool:
    # 단독 EXE나 임의 폴더명은 공식 타이틀과 우연히 같아도 확정 근거가 안 됨.
    return any(clue.kind == "title" and clue.source in {
        "archive_name", "readme", "root_folder",
    } and _name_matches(clue.value, external) for clue in scan.clues)


def analyze_identity(
    path: Path,
    *,
    classifier: Callable[[str], SearchDecision] | None = None,
    max_queries: int = MAX_SEARCHES_DETAILED,
    online: bool = True,
    scan: SimpleScan | None = None,
    progress: Callable[[str], None] | None = None,
) -> SimpleResult:
    """종합 검색과 '외부 작품 식별' 판정. 실제 게임 바이너리 동일성은 미인증."""
    begin = time.perf_counter()

    def notify(message: str) -> None:
        if progress is not None:
            try:
                progress(message)
            except Exception:
                pass

    path = Path(path)
    notify("이름·품번 근거 수집 중")
    local = scan if scan and scan.archive_name == path.name else collect_identity_clues(path)
    notes = list(local.notes)
    if local.scan_state == "invalid":
        return SimpleResult(path.name, "unidentified", "", "", "지원하지 않는 파일",
                            local, (), (), (), tuple(notes),
                            round(time.perf_counter() - begin, 3))
    notify("이름·품번 검색 중")
    plan = _queries(local, max_queries)
    if online and classifier is None:
        from .enhanced_search import enhanced_classify_game
        classifier = enhanced_classify_game
    attempts: list[SimpleAttempt] = []
    if online and classifier is not None:
        for query, basis in plan:
            try:
                decision = classifier(query)
            except Exception as exc:
                decision = SearchDecision(
                    "lookup_unavailable", query,
                    reason="검색 서비스 오류: " + type(exc).__name__,
                    search_state="network_error",
                )
            attempts.append(SimpleAttempt(query, basis, decision))
    notify("외부 작품명·품번 대조 중")
    if not online:
        return SimpleResult(
            path.name, "unidentified", "", "", "오프라인 모드: 이름과 품번만 수집",
            local, (), (), tuple(q for q, _ in plan), tuple(notes),
            round(time.perf_counter() - begin, 3),
        )

    official: dict[tuple[str, str], SearchDecision] = {}
    weak: dict[str, str] = {}
    errors = []
    for item in attempts:
        d = item.decision
        if d.search_state in {"network_error", "cooldown_skipped"}:
            errors.append(item.query)
        if not d.proposed_title:
            continue
        if d.status == "confirmed_game" and d.dlsite_code:
            key = ("dlsite", d.dlsite_code.upper())
            official.setdefault(key, d)
        elif d.status == "platform_confirmed_game" and d.source_id:
            key = ("steam", d.source_id)
            official.setdefault(key, d)
        elif d.status in {"internet_confirmed_game", "internet_candidate"}:
            weak.setdefault(_key(d.proposed_title), d.proposed_title)

    official_rows = list(official.items())
    codes = {x.value.upper() for x in local.clues if x.kind == "product_code"}
    aligned = [
        (key, d) for key, d in official_rows
        if (key[1].upper() in codes or
            ("Steam App ID: " + key[1]).upper() in codes)
    ]
    if len(official_rows) > 1 and len(aligned) == 1:
        # 파일명/README의 명시적 제품번호 하나가 여러 공식 결과 중
        # 단독으로 일치하더라도 무관한 별개 작품 가능성을 무시하지 않는다.
        notes.append("외부에서 서로 다른 공식 상품 ID가 조회되었습니다.")
    if len(official_rows) > 1:
        status = "multiple"
        chosen = None
        reason = "서로 다른 공식 상품 식별자가 발견되었습니다. 임의로 병합하지 않습니다."
    elif len(official_rows) == 1:
        key, chosen = official_rows[0]
        matched_title = _match_any_title(local, chosen.proposed_title)
        # 진짜 로컬 파일 내용은 검사하지 않으므로 '공식 작품 식별'만 의미.
        if matched_title and (not local.exe_ambiguous) and (
            not codes or key[1].upper() in codes or
            ("Steam App ID: " + key[1]).upper() in codes
        ):
            status = "identified"
            reason = "공식 등록 작품명과 로컬에서 수집한 이름이 일치합니다. "
            reason += "실제 게임 파일의 진위·버전·언어는 아직 확인하지 않았습니다."
        else:
            status = "likely"
            reason = "공식 작품은 발견했지만 이름·품번 교차검증이 충분하지 않습니다."
        if local.exe_ambiguous:
            reason += " 여러 실행파일 이름이 서로 달라 수동 확인이 필요합니다."
    elif weak:
        status = "likely" if len(weak) == 1 else "multiple"
        chosen = None
        reason = "웹 작품명 후보는 있으나 공식 작품번호와 충분한 연결 근거가 없습니다."
    else:
        status = "search_error" if errors else "unidentified"
        chosen = None
        reason = ("일부 검색이 실패했습니다. 작품이 없다는 뜻은 아닙니다."
                  if errors else "이름·품번으로 외부 작품 정체를 확인하지 못했습니다.")
    if local.scan_state in {"partial", "limit_exceeded", "unavailable"} and status == "identified":
        status = "likely"
        reason = "압축파일 내부 이름 목록이 불완전하므로 공식 후보 확인에 머물렀습니다."
    if local.encryption_state != "clear" and status == "identified":
        status = "likely"
        reason = "암호화 또는 암호 상태 미확인: 파일명 근거만 사용했습니다."

    best_title = (chosen.proposed_title if chosen is not None else
                  next(iter(weak.values()), "") if len(weak) == 1 else "")
    product_code = (official_rows[0][0][1] if chosen is not None else "")
    alternatives = tuple(dict.fromkeys(
        [d.proposed_title + " (" + key[0] + ":" + key[1] + ")"
         for key, d in official_rows]
        + list(weak.values())
    ))
    return SimpleResult(
        path.name, status, best_title, product_code, reason, local,
        tuple(attempts), alternatives, tuple(q for q, _ in plan),
        tuple(notes), round(time.perf_counter() - begin, 3),
    )
