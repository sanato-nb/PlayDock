"""PlayDock v0.11 — 압축파일 *이름만* 사용하는 독립 정체 판독 실험.

ZIP/7z/RAR을 열거나 내용/내부 경로/README/EXE를 검사하지 않는다.
공식 작품번호가 있으면 동일 코드의 공식 상품을 직접 조회하고,
없으면 정제한 게임명으로 단일 웹 검색만 수행한다.
타임아웃은 데몬 스레드 + 서비스별 단일 슬롯으로 상한을 둔다.
웹 검색 결과만으로 로컬 압축파일의 실제 내용이나 진위를 인증하지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from queue import Empty, Queue
import re
from threading import Lock, Thread
import time
from typing import Callable
from urllib.parse import urlsplit

from .catalog_aliases import DISTRIBUTION_PREFIX, explicit_title_keys
from .detector import (
    CODE_PATTERN, GAME_TYPES, Product, fetch_product, normalized_title,
    product_page_candidate,
)
from .identity_hints import extract_hints
from .pipeline import WebEvidence, examine_web_results, fast_web_search
from .search_terms import cleaned_search_title
from .steam_client import SteamProduct, fetch_steam_product
from .storefront_candidate import single_store_candidate
from .filename_web_search import isolated_web_search
from .no_api_html import fetch_dlsite_html, fetch_steam_html
from .filename_page_rank import page_score, steam_app_id, chapter_number

VERSION = "0.11.7-no-api-test"
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
    archive_kind: str = "unknown"

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
    web_raw_results: tuple[dict, ...] = ()
    web_evidence: tuple[WebEvidence, ...] = ()
    search_providers: tuple[dict, ...] = ()
    rejected_pages: tuple[dict, ...] = ()
    web_code_hints: tuple[dict, ...] = ()

    @property
    def is_unresolved(self) -> bool:
        # 품번으로 공식 등록 작품을 확인한 건은 미발견과 별개로 집계한다.
        # 이 결과도 게임 파일 내용·버전의 인증은 아니다.
        return self.status not in {"official_match", "catalog_found"}

    @property
    def label(self) -> str:
        return {
            "official_match": "공식 상품명 일치",
            "catalog_found": "품번으로 공식 상품 발견 · 제목 미검증",
            "web_candidate": "웹에서 게임명 단서 발견 · 미검증",
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
        archive_kind=hint.archive_kind,
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
    note = ("공식 상품 페이지에서 게임 유형은 미검증"
            if not p.work_type else
            "공식 등록 상품이 게임 유형이 아닙니다"
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
    # 검색 공급자 계측 정보를 보존하기 위해 list 슬라이스를 하지 않는다.
    return isolated_web_search(title)


def _web_name_candidate(
    local: str, evidence: tuple[WebEvidence, ...], *,
    filename: str = "",
) -> WebEvidence | None:
    """개발자 프로필·다른 챕터 대신 작품별 게임 페이지를 우선한다.

    반환된 페이지도 웹 단서이지 압축 내용/게임 정체의 확정은 아니다.
    """
    scored = []
    for ev in evidence:
        score = page_score(
            local, ev.title, ev.url,
            local_filename=filename,
            snippet="game" if ev.game_context else "",
        )
        if score:
            scored.append((score, ev))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1] if scored else None



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
    serper_api_key: str = "",
    no_api: bool = False,
) -> FilenameIdentityResult:
    start = time.monotonic()
    clues = extract_filename_clues(filename)
    if no_api:
        # Strict standalone mode: no JSON API endpoints or paid searches.
        # Injected callbacks remain available to offline unit tests only.
        if dlsite_lookup is _direct_dlsite_lookup:
            dlsite_lookup = fetch_dlsite_html
        if steam_lookup is _direct_steam_lookup:
            steam_lookup = fetch_steam_html

    def official_candidate(candidate: Candidate) -> Candidate:
        if not no_api:
            return candidate
        note = candidate.notes or "공식 공개 HTML 페이지에서 게임 유형은 미검증"
        return replace(candidate, source="official_html", notes=note)

    found: dict[tuple[str, str], Candidate] = {}
    looked: list[str] = []
    errors: list[str] = []
    raw_hits: list[dict] = []
    web_evidence: tuple[WebEvidence, ...] = ()
    providers: tuple[dict, ...] = ()
    rejected_pages: list[dict] = []
    web_codes: list[dict] = []

    def check_code(code: str) -> None:
        looked.append("DLsite " + code)
        try:
            product = _CODE_GATE.call(lambda: dlsite_lookup(code), code_timeout)
            if product is not None and product.code.upper() == code.upper():
                found[("dlsite", code)] = official_candidate(
                    _product_to_candidate(product, clues.game_name)
                )
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
                found[("steam", sid)] = official_candidate(
                    _steam_to_candidate(product, clues.game_name)
                )
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
                if web_search is _single_title_search:
                    # 기본 검색은 자식 프로세스 자체가 제한시간 후 완전히
                    # 종료된다. 전역 스레드 잠금을 사용하지 않는다.
                    chapter = chapter_number(clues.archive_name)
                    rows = (
                        isolated_web_search(
                            clues.game_name,
                            serper_api_key="" if no_api else serper_api_key,
                            no_api=no_api,
                            **({"chapter_hint": chapter} if chapter else {}),
                        ) if (no_api or serper_api_key or chapter)
                        else web_search(clues.game_name)
                    )
                else:
                    # 테스트/플러그인에서 주입한 임의 콜백은 여전히
                    # bounded thread에서 처리하되 기본 서비스와 분리한다.
                    rows = _TITLE_GATE.call(
                        lambda: web_search(clues.game_name), web_timeout
                    )
                raw_hits = [
                    {
                        "title": str(row.get("title") or "")[:220],
                        "url": str(row.get("href") or row.get("url") or "")[:1000],
                    }
                    for row in list(rows)[:MAX_WEB_RESULTS]
                    if isinstance(row, dict)
                ]
                providers = tuple(getattr(rows, "providers", ()))
                evidence = examine_web_results(clues.game_name, list(rows))
                web_evidence = evidence
                # 먼저 공식 DLsite 작품별 URL만 검증한다. 일반 검색
                # 결과의 품번은 보조 힌트이며, 공식 조회 전에는 후보가 아니다.
                official_hits = []
                third_party = []
                seen_codes = set()
                for ev in evidence:
                    if not page_score(
                        clues.game_name, ev.title, ev.url,
                        local_filename=clues.archive_name,
                        snippet="game" if ev.game_context else "",
                    ):
                        continue
                    hit = product_page_candidate(ev.url)
                    if hit:
                        code, category = hit
                        if code not in seen_codes:
                            official_hits.append((code, category, ev.url))
                            seen_codes.add(code)
                        continue
                    # 설명문만의 품번은 해당 게임과의 연결이 약해 제외한다.
                    # 제목 또는 URL에 드러난 품번만 공식 카탈로그로 재검증.
                    for code in CODE_PATTERN.findall(ev.title + " " + ev.url):
                        code = code.upper()
                        if code not in seen_codes:
                            third_party.append((code, None, ev.url))
                            seen_codes.add(code)
                for code, category, evidence_url in (
                    official_hits + third_party
                )[:MAX_WEB_CODES]:
                    is_official_url = category is not None
                    looked.append(
                        ("DLsite 공식 페이지 " if is_official_url else
                         "웹 품번 공식 재검증 ") + code
                    )
                    record = {
                        "code": code, "evidence_url": evidence_url,
                        "origin": "official_product_url" if is_official_url else
                                  "third_party_search_result",
                        "state": "unverified",
                    }
                    try:
                        def verify_code(code=code, category=category):
                            if no_api:
                                return fetch_dlsite_html(code, timeout=2.5)
                            if category:
                                return fetch_product(
                                    code, categories=(category,), timeout=2.0
                                )
                            return fetch_product(code, timeout=2.0)
                        p = _CODE_GATE.call(verify_code, code_timeout)
                        if p is None:
                            record["state"] = "catalog_not_verified"
                        elif p.code.upper() != code:
                            record["state"] = "id_mismatch"
                        elif not _title_matches(clues.game_name, p.title):
                            record["state"] = "title_mismatch"
                            rejected_pages.append({
                                "url": evidence_url, "reason":
                                "공식 상품 이름이 압축파일명과 다릅니다",
                                "official_title": p.title[:160],
                            })
                        else:
                            record["state"] = "official_title_verified"
                            c = official_candidate(
                                _product_to_candidate(p, clues.game_name)
                            )
                            if not is_official_url:
                                # 검색 기사에서 발견한 번호는 파일명에 직접
                                # 적힌 번호와 다르므로 단독 확정으로 승격 금지.
                                c = Candidate(
                                    c.title, c.platform, c.product_id, c.url,
                                    "search_official_recheck", c.name_matches,
                                    c.work_type,
                                    "제3자 검색 결과의 품번을 공식 카탈로그에서 "
                                    "재조회함. 파일 내용 및 상품 동일성 미검증.",
                                )
                            found[("dlsite", code)] = c
                    except Exception as exc:
                        record["state"] = "lookup_error"
                        record["error"] = type(exc).__name__
                        errors.append(
                            "DLsite 웹 품번 검증 실패: " + type(exc).__name__
                        )
                    web_codes.append(record)
                # 검색 결과에 실제 작품 URL이 있으면 그 slug를 먼저
                # 대조한다. Steam 후보의 제목은 검색 스니펫이 아닌
                # 공식 Steam 조회 결과로 재검증한다.
                checked_steam = set()
                excluded_urls = set()
                for ev in evidence:
                    sid = steam_app_id(
                        clues.game_name, ev.title, ev.url,
                        local_filename=clues.archive_name,
                    )
                    if not sid or sid in checked_steam:
                        continue
                    checked_steam.add(sid)
                    looked.append("Steam 웹 후보 " + sid)
                    try:
                        p = _STEAM_GATE.call(
                            lambda sid=sid: steam_lookup(sid), steam_timeout
                        )
                        if (p is not None and p.app_id == sid
                                and p.item_type == "game"
                                and _title_matches(clues.game_name, p.title)):
                            found[("steam", sid)] = official_candidate(
                                _steam_to_candidate(p, clues.game_name)
                            )
                        elif p is not None and p.app_id == sid:
                            excluded_urls.add(ev.url)
                            rejected_pages.append({
                                "url": ev.url, "reason":
                                "Steam 공식 상품 이름/상품 유형이 파일명과 다릅니다",
                                "official_title": p.title[:160],
                            })
                    except Exception as exc:
                        errors.append(
                            "Steam 웹 후보 " + sid + ": "
                            + type(exc).__name__
                        )
                    if len(checked_steam) >= 2:
                        break
                if not found:
                    clue = _web_name_candidate(
                        clues.game_name,
                        tuple(ev for ev in evidence
                              if ev.url not in excluded_urls
                              and not any(x["url"] == ev.url
                                          for x in rejected_pages)),
                        filename=clues.archive_name,
                    )
                    if clue is not None:
                        score = page_score(
                            clues.game_name, clue.title, clue.url,
                            local_filename=clues.archive_name,
                            snippet="game" if clue.game_context else "",
                        )
                        source_note = (
                            "게임 작품별 판매 페이지로 보이는 URL이지만 "
                            "게임 파일 내용이나 공식 등록 원문은 미검증."
                            if score >= 75 else
                            "일반 웹 기사·하위 페이지의 이름 단서만 확인. "
                            "게임 본편 및 공식 작품 페이지 여부는 미검증."
                        )
                        found[("web", clue.url)] = Candidate(
                            clues.game_name, clue.domain, "", clue.url,
                            "web_search", True, "", source_note,
                        )
            except Exception as exc:
                providers = tuple(getattr(exc, "providers", ()))
                errors.append(
                    "제목 검색 실패: " + type(exc).__name__ + ": "
                    + str(exc)[:220]
                )
    else:
        looked.append("오프라인: 외부 검색 미실행")

    candidates = tuple(found.values())
    # 본편이 아닌 별도 파일이라는 명시적 이름 단서는
    # 공식 게임 상품명과 같더라도 본편으로 단독 확정하지 않는다.
    distinct_package = clues.archive_kind in {
        "patch_candidate", "dlc_candidate", "modpack_candidate",
        "server_package_candidate", "bundle_candidate",
    }
    strong = [
        c for c in candidates
        if (c.source == "official_api" and c.name_matches
            and c.work_type in GAME_TYPES | {"game"}
            and not c.notes and not distinct_package)
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
    elif (
        no_api and len(candidates) == 1
        and (clues.product_codes or clues.steam_ids)
        and candidates[0].source == "official_html"
    ):
        status = "catalog_found"
        reason = (
            "공식 사이트의 공개 HTML 페이지에서 파일명에 적힌 상품번호를 "
            "확인했습니다. 상품명·게임 유형·파일 내용은 별도 검증이 필요합니다."
        )
    elif (
        len(candidates) == 1
        and (clues.product_codes or clues.steam_ids)
        and candidates[0].source == "official_api"
        and candidates[0].work_type in GAME_TYPES | {"game"}
        and not candidates[0].notes
        and not distinct_package
        and (
            not clues.game_name
            or bool(re.search(r"[가-힣ぁ-んァ-ヶ一-龯]", clues.game_name))
                != bool(re.search(r"[가-힣ぁ-んァ-ヶ一-龯]",
                                  candidates[0].title))
            or (bool(re.search(r"[가-힣]", clues.game_name))
                and bool(re.search(r"[ぁ-んァ-ヶ]", candidates[0].title)))
        )
    ):
        status = "catalog_found"
        reason = (
            "파일명에 적힌 품번으로 공식 등록 상품을 찾았습니다. "
            "제목이 없거나 언어가 달라 이름 일치는 검증되지 않았고, "
            "실제 압축파일 내용의 정체도 아직 확인하지 않았습니다."
        )
    elif len(candidates) == 1 and candidates[0].source == "web_search":
        status = "web_candidate"
        reason = (
            "검색 페이지에서 파일명과 관련된 게임 단서를 찾았습니다. "
            "공식 상품이나 압축파일의 정체로 확정하지 않았습니다."
        )
    elif candidates:
        status = "likely"
        reason = (
            "파일명에 DLC·모드·패치·서버팩·합본 표기가 있어 본편과 동일시할 "
            "수 없습니다. " if distinct_package else ""
        ) + ("공식 상품은 발견했지만 이름이 다르거나 별도 패치 상품이거나 "
             "웹 검색 결과만 확인되어 수동 검토가 필요합니다.")
    elif errors:
        status = "search_error"
        reason = "외부 조회 실패 또는 제한시간 초과. 게임이 없다는 뜻이 아닙니다."
    else:
        status = "unidentified"
        if rejected_pages:
            reason = (
                "검색한 공식 상품의 제목이나 유형이 압축파일명과 달라 "
                "후보에서 제외했습니다."
            )
        elif raw_hits:
            reason = (
                f"웹 검색 결과 {len(raw_hits)}건은 받았지만 "
                "공식 작품 또는 이름이 일치하는 유력 단서를 선정하지 못했습니다."
            )
        elif any(q.startswith("제목 ") for q in looked):
            reason = "제목 검색이 0건을 반환했습니다. 웹에 게임이 없다는 의미는 아닙니다."
        else:
            reason = "파일명만으로 확인 가능한 작품을 찾지 못했습니다."

    candidate = candidates[0] if len(candidates) == 1 else None
    return FilenameIdentityResult(
        clues.archive_name, clues, status,
        candidate.title if candidate else "",
        candidate.product_id if candidate else "",
        reason, candidates, tuple(looked), tuple(errors),
        round(time.monotonic() - start, 3),
        tuple(raw_hits), web_evidence, providers,
        tuple(rejected_pages), tuple(web_codes),
    )
