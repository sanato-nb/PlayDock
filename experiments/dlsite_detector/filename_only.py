"""PlayDock v0.11 — 압축파일 *이름만* 사용하는 독립 정체 판독 실험.

ZIP/7z/RAR을 열거나 내용/내부 경로/README/EXE를 검사하지 않는다.
공식 작품번호가 있으면 동일 코드의 공식 상품을 직접 조회하고,
없으면 정제한 게임명으로 단일 웹 검색만 수행한다.
타임아웃은 데몬 스레드 + 서비스별 단일 슬롯으로 상한을 둔다.
웹 검색 결과만으로 로컬 압축파일의 실제 내용이나 진위를 인증하지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty, Queue
import re
from threading import Lock, Thread
import time
from typing import Callable
from urllib.parse import urlsplit

from .catalog_aliases import DISTRIBUTION_PREFIX, explicit_title_keys
from .detector import (
    GAME_TYPES, Product, fetch_product, normalized_title, product_page_candidate,
)
from .identity_hints import extract_hints
from .pipeline import examine_web_results, fast_web_search
from .search_terms import cleaned_search_title
from .steam_client import SteamProduct, fetch_steam_product
from .storefront_candidate import single_store_candidate

VERSION = "0.11-test"
MAX_CODES = 3
MAX_WEB_RESULTS = 6
MAX_WEB_CODES = 2
CODE_LIMIT_SECONDS = 8.0
TITLE_LIMIT_SECONDS = 8.0
STEAM_LIMIT_SECONDS = 6.0

PATCH_PREFIX = re.compile(
    r"(?i)^\s*(?:【|\[)?\s*(?:AI\s*번역|AI\s*翻訳|번역\s*패치|翻訳\s*パッチ|"
    r"translation\s*patch|translation\s*only)"
)


class LookupBusy(RuntimeError):
    pass


class LookupTimedOut(TimeoutError):
    pass


class _BoundedGate:
    """백엔드 스레드가 멈춰도 GUI가 기다리지 않고 스레드가 증식하지 않는다.

    기존 느린 요청이 아직 수행 중이면 추가 요청을 시작하지 않고 검색
    장애로 분리한다. 실제 소켓 연결을 강제로 끊는 것은 아니므로
    오래 걸린 요청의 백그라운드 종료 여부는 독립적으로 관리한다.
    """
    def __init__(self):
        self._lock = Lock()

    def call(self, fn: Callable[[], object], timeout: float) -> object:
        if not self._lock.acquire(blocking=False):
            raise LookupBusy("앞선 외부 조회가 아직 종료되지 않았습니다")
        q: Queue = Queue(maxsize=1)

        def work():
            try:
                q.put((True, fn()))
            except Exception as exc:
                q.put((False, exc))
            finally:
                self._lock.release()

        Thread(target=work, daemon=True).start()
        try:
            ok, value = q.get(timeout=max(0.1, timeout))
        except Empty as exc:
            raise LookupTimedOut(f"외부 조회 제한시간 {timeout:.0f}초 초과") from exc
        if not ok:
            raise value
        return value


_CODE_GATE = _BoundedGate()
_TITLE_GATE = _BoundedGate()
_STEAM_GATE = _BoundedGate()


@dataclass(frozen=True)
class FilenameClues:
    archive_name: str
    game_name: str
    product_codes: tuple[str, ...]
    steam_ids: tuple[str, ...]
    source: str = "archive_filename_only"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    title: str
    platform: str
    product_id: str
    url: str
    source: str  # official_api / search_result
    name_matches: bool
    work_type: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FilenameIdentityResult:
    filename: str
    extracted: FilenameClues
    status: str  # official_match/likely/multiple/unidentified/search_error
    best_title: str
    product_id: str
    reason: str
    candidates: tuple[Candidate, ...]
    lookups: tuple[str, ...]
    errors: tuple[str, ...]
    elapsed_seconds: float

    @property
    def is_unresolved(self) -> bool:
        return self.status != "official_match"

    @property
    def label(self) -> str:
        return {
            "official_match": "공식 상품명 일치",
            "likely": "후보 · 추가 검증 필요",
            "multiple": "복수 상품 후보",
            "unidentified": "정체 미확인",
            "search_error": "검색 장애 · 재검사",
        }[self.status]

    def to_dict(self) -> dict:
        out = asdict(self)
        out["extracted"] = self.extracted.to_dict()
        out["candidates"] = [c.to_dict() for c in self.candidates]
        out["is_unresolved"] = self.is_unresolved
        out["label"] = self.label
        out["archive_contents_inspected"] = False
        out["local_game_files_verified"] = False
        out["post_identity_checks"] = "deferred"
        return out


def extract_filename_clues(value: str) -> FilenameClues:
    """외부 검색에는 basename에서 유도된 게임명과 ID만 제공."""
    name = re.split(r"[/\\]", str(value))[-1].strip()
    hint = extract_hints(name)
    title = cleaned_search_title(name)
    # 제목이 공식 코드만으로 구성되거나 전부 숫자인 경우는 무제목.
    if title and not any(ch.isalpha() for ch in title):
        title = ""
    return FilenameClues(
        name, title,
        tuple(dict.fromkeys(code.upper() for code in hint.dlsite_codes))[:MAX_CODES],
        tuple(dict.fromkeys(hint.steam_app_ids))[:MAX_CODES],
    )


def _title_matches(local: str, official: str) -> bool:
    if not local or not official:
        return False
    official_clean = DISTRIBUTION_PREFIX.sub("", official).strip()
    key = normalized_title(local)
    if not key or len(key) < 4:
        return False
    if key in explicit_title_keys(official_clean):
        return True
    # 명시적 이중 언어 제목: '영문 원제 - 현지어 부제' 등.
    # 임의의 짧은 공통 문자열(예: Game, Love)은 별칭으로 인정하지 않는다.
    parts = re.split(r"\s+[-–—|]\s+|[~～]", local)
    if len(parts) > 1:
        first = normalized_title(parts[0])
        if len(first) >= 9 and first in explicit_title_keys(official_clean):
            return True
    return False


def _product_to_candidate(p: Product, local: str) -> Candidate:
    is_game = p.work_type in GAME_TYPES
    match = _title_matches(local, p.title)
    note = ("공식 등록 상품이 게임 유형이 아닙니다"
            if not is_game else
            "공식 상품명에 번역 패치 표기가 있습니다"
            if PATCH_PREFIX.match(p.title) else "")
    return Candidate(p.title, "dlsite", p.code, p.url, "official_api",
                     match, p.work_type, note)


def _steam_to_candidate(p: SteamProduct, local: str) -> Candidate:
    note = "" if p.item_type == "game" else "Steam 상품 유형이 본편 게임이 아닙니다"
    return Candidate(p.title, "steam", p.app_id, p.url, "official_api",
                     _title_matches(local, p.title), p.item_type, note)


def _direct_dlsite_lookup(code: str) -> Product | None:
    # 비공식 공개 JSON의 모든 공식 카테고리를 확인하되 각 요청은 짧게 제한.
    return fetch_product(code, timeout=2.0)


def _direct_steam_lookup(sid: str) -> SteamProduct | None:
    return fetch_steam_product(sid, timeout=4.0)


def _single_title_search(title: str) -> list[dict]:
    # DDGS 1회, 일반 검색어 1개. 여러 백엔드 시도는 하지 않는다.
    return fast_web_search(title)[:MAX_WEB_RESULTS]


def identify_filename(
    filename: str,
    *,
    dlsite_lookup: Callable[[str], Product | None] = _direct_dlsite_lookup,
    steam_lookup: Callable[[str], SteamProduct | None] = _direct_steam_lookup,
    web_search: Callable[[str], list[dict]] = _single_title_search,
    code_timeout: float = CODE_LIMIT_SECONDS,
    web_timeout: float = TITLE_LIMIT_SECONDS,
    steam_timeout: float = STEAM_LIMIT_SECONDS,
    online: bool = True,
) -> FilenameIdentityResult:
    start = time.monotonic()
    clues = extract_filename_clues(filename)
    found: dict[tuple[str, str], Candidate] = {}
    looked: list[str] = []
    errors: list[str] = []

    def check_code(code: str) -> None:
        looked.append("DLsite " + code)
        try:
            product = _CODE_GATE.call(lambda: dlsite_lookup(code), code_timeout)
            if product is not None and product.code.upper() == code.upper():
                found[("dlsite", code)] = _product_to_candidate(product, clues.game_name)
            elif product is not None:
                errors.append("공식 조회에서 다른 상품번호가 반환됨: " + code)
        except (LookupTimedOut, LookupBusy, Exception) as exc:
            # 모든 통신 장애를 '없는 작품'으로 바꾸지 않음.
            errors.append("DLsite " + code + " 조회 실패: " + type(exc).__name__)

    def check_steam(sid: str) -> None:
        looked.append("Steam App ID " + sid)
        try:
            product = _STEAM_GATE.call(lambda: steam_lookup(sid), steam_timeout)
            if product is not None and product.app_id == sid:
                found[("steam", sid)] = _steam_to_candidate(product, clues.game_name)
            elif product is not None:
                errors.append("Steam에서 다른 App ID가 반환됨: " + sid)
        except Exception as exc:
            errors.append("Steam " + sid + " 조회 실패: " + type(exc).__name__)

    if online:
        for code in clues.product_codes:
            check_code(code)
        for sid in clues.steam_ids:
            check_steam(sid)

        # 코드가 발견되었으면 그 코드의 실제 등록명을 우선 대조한다.
        # ID 등록 여부조차 판단할 수 없을 때마다 추가 제목 검색을
        # 수행하면 이전 버전처럼 타임아웃이 누적되므로 재검사로 둔다.
        if not (clues.product_codes or clues.steam_ids) and clues.game_name:
            looked.append("제목 " + clues.game_name)
            try:
                rows = _TITLE_GATE.call(
                    lambda: web_search(clues.game_name), web_timeout
                )
                evidence = examine_web_results(clues.game_name, list(rows))
                # 정확한 DLsite 작품별 공식 URL만 조회. 다른 사이트 제목은
                # 제품번호의 근거가 되지 않는다.
                official_hits = []
                for ev in evidence:
                    hit = product_page_candidate(ev.url)
                    if hit and hit[0] not in [h[0] for h in official_hits]:
                        official_hits.append(hit)
                for code, category in official_hits[:MAX_WEB_CODES]:
                    looked.append("DLsite 후보 " + code)
                    try:
                        p = _CODE_GATE.call(
                            lambda code=code, category=category: fetch_product(
                                code, categories=(category,), timeout=2.0
                            ), code_timeout
                        )
                        if p is not None and p.code.upper() == code.upper():
                            found[("dlsite", code)] = _product_to_candidate(
                                p, clues.game_name
                            )
                    except Exception as exc:
                        errors.append("DLsite 후보 검증 실패: " + type(exc).__name__)
                # 검색 결과만으로 직접 공식 게임 확정하지 않는다.
                candidate = single_store_candidate(clues.game_name, evidence)
                if candidate is not None:
                    title, platform, url = candidate
                    if platform == "steam":
                        parsed = urlsplit(url)
                        match = re.search(r"^/app/([1-9]\d{2,9})(?:/|$)", parsed.path)
                        if match:
                            check_steam(match.group(1))
                    if platform == "itch.io" and not found:
                        found[("itch.io", url)] = Candidate(
                            title, "itch.io", "", url, "search_result", True,
                            notes="검색 결과만 확인; 작품 원문은 검증하지 않았습니다"
                        )
            except Exception as exc:
                errors.append("제목 검색 실패: " + type(exc).__name__)
    else:
        looked.append("오프라인: 외부 검색 미실행")

    candidates = tuple(found.values())
    strong = [
        c for c in candidates
        if (c.source == "official_api" and c.name_matches
            and c.work_type in GAME_TYPES | {"game"}
            and not c.notes)
    ]
    if not online:
        status = "unidentified"
        reason = "오프라인: 압축파일 이름에서 이름·품번만 추출했습니다."
    elif len(candidates) > 1:
        status = "multiple"
        reason = "서로 다른 상품 후보가 있어 자동으로 하나를 선택하지 않습니다."
    elif len(strong) == 1 and len(candidates) == 1:
        status = "official_match"
        reason = ("공식 카탈로그에서 작품번호·작품명과 게임 유형을 확인했습니다. "
                  "압축파일의 내용 자체는 검사하거나 인증하지 않았습니다.")
    elif candidates:
        status = "likely"
        reason = ("공식 상품은 발견했지만 이름이 다르거나 별도 패치 상품이거나 "
                  "웹 검색 결과만 확인되어 수동 검토가 필요합니다.")
    elif errors:
        status = "search_error"
        reason = "외부 조회 실패 또는 제한시간 초과. 게임이 없다는 뜻이 아닙니다."
    else:
        status = "unidentified"
        reason = "파일명만으로 확인 가능한 작품을 찾지 못했습니다."

    candidate = candidates[0] if len(candidates) == 1 else None
    return FilenameIdentityResult(
        clues.archive_name, clues, status,
        candidate.title if candidate else "",
        candidate.product_id if candidate else "",
        reason, candidates, tuple(looked), tuple(errors),
        round(time.monotonic() - start, 3),
    )
