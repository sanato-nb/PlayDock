"""DLsite 판별 뒤 일반 웹 검색으로 넘어가는 독립 2단계 검색 파이프라인.

UI/PlayDock 본체/DB에 의존하지 않는다. 자동 판별은 데이터 수정으로 이어지지 않는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable
from urllib.parse import urlsplit
import ipaddress
import re

from .detector import Detection, detect_dlsite_game, normalized_title, _clean_input_title
from .search_terms import cleaned_search_title, search_title_variants


@dataclass(frozen=True)
class WebEvidence:
    title: str
    url: str
    domain: str
    strong_match: bool
    game_context: bool
    trusted_source: bool


@dataclass(frozen=True)
class SearchDecision:
    status: str
    original_query: str
    proposed_title: str = ""
    dlsite_status: str = ""
    dlsite_code: str = ""
    reason: str = ""
    web_checked: bool = False
    evidence: tuple[WebEvidence, ...] = ()
    source_platform: str = ""
    source_id: str = ""
    source_url: str = ""
    archive_kind: str = "unknown"

    @property
    def label(self) -> str:
        return {
            "confirmed_game": "DLsite 게임 확인 · 통과",
            "suspected_non_game": "비게임으로 추정 · 별도 분류",
            "internet_confirmed_game": "인터넷 검색으로 게임 확인",
            "internet_candidate": "인터넷에서 게임 후보 발견 · 원본 확인 필요",
            "platform_confirmed_game": "Steam 작품 코드·게임 유형 확인",
            "lookup_unavailable": "조회 불가 · 별도 보관",
            "input_error": "입력 오류",
        }[self.status]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["label"] = self.label
        return result


# 실험용 출처 목록. 사이트 도메인만으로 게임 여부를 확정하지 않는다.
GAME_SITES = (
    "store.steampowered.com", "gog.com", "itch.io", "mobygames.com",
    "pcgamingwiki.com", "igdb.com", "nintendo.com", "playstation.com",
    "xbox.com", "metacritic.com",
)
GAME_WORDS = re.compile(r"\b(?:video game|pc game|gameplay|game|games|gaming)\b|게임|ゲーム", re.I)
HEADLINE_SEPARATORS = (" | ", " - ", " — ", " – ", " :: ")


def _safe_host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return ""
        if host in {"localhost"} or host.endswith((".local", ".localhost", ".internal")):
            return ""
        try:
            ipaddress.ip_address(host)
            return ""
        except ValueError:
            pass
        if "." not in host:
            return ""
        return host
    except (ValueError, TypeError, AttributeError):
        return ""


def _source_group(host: str) -> str:
    for site in GAME_SITES:
        if host == site or host.endswith("." + site):
            return site
    return host.removeprefix("www.")


def _is_trusted(host: str) -> bool:
    return any(host == site or host.endswith("." + site) for site in GAME_SITES)


def _heading_matches(local: str, heading: str) -> bool:
    for segment in [heading] + [heading.split(sep, 1)[0] for sep in HEADLINE_SEPARATORS]:
        if normalized_title(segment) == local:
            return True
    return False


def default_web_search(query: str) -> list[dict]:
    """언어별 검색식과 완전 일치 검색을 차례로 수행하는 bounded 검색 연결기.

    한 번의 검색이 실패해도 다음 검색식을 시도한다. 사용자 경로나
    압축파일 내부 파일 목록은 전송하지 않는다.
    """
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("일반 인터넷 검색에 ddgs 패키지가 필요합니다.") from exc
    clean = cleaned_search_title(query)
    if not clean:
        return []
    if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in clean):
        qualifier = "ゲーム"
    elif any("\uac00" <= ch <= "\ud7a3" for ch in clean):
        qualifier = "게임"
    else:
        qualifier = "game"
    searches = (f'"{clean}" {qualifier}', f'"{clean}"')
    records = []
    seen = set()
    errors = []
    with DDGS(timeout=12) as client:
        for phrase in searches:
            try:
                for item in (client.text(phrase, max_results=8) or []):
                    if not isinstance(item, dict):
                        continue
                    url = item.get("href") or item.get("url")
                    if url and url not in seen:
                        seen.add(url)
                        records.append(item)
            except Exception as exc:
                errors.append(type(exc).__name__)
    if not records and errors:
        raise RuntimeError("일반 인터넷 검색 실패: " + ", ".join(errors))
    return records[:16]


def fast_web_search(query: str) -> list[dict]:
    """검증판 빠른 모드: 제한된 단일 웹 요청, 결과 6개, 짧은 네트워크 제한.

    상세 모드의 이중 검색과 달리 첫 요청이 실패해도 반복하지 않는다.
    검색 오류는 추후 판정의 limitations에 남긴다.
    """
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("일반 인터넷 검색에 ddgs 패키지가 필요합니다.") from exc
    clean = cleaned_search_title(query)
    if not clean:
        return []
    if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in clean):
        qualifier = "ゲーム"
    elif any("\uac00" <= ch <= "\ud7a3" for ch in clean):
        qualifier = "게임"
    else:
        qualifier = "game"
    try:
        with DDGS(timeout=6) as client:
            return list(client.text(f'"{clean}" {qualifier}', max_results=6) or [])[:6]
    except Exception as exc:
        raise RuntimeError("빠른 웹 검색 오류: " + type(exc).__name__) from exc


def examine_web_results(query: str, records: list[dict]) -> tuple[WebEvidence, ...]:
    local = normalized_title(query)
    seen = set()
    collected = []
    for row in records[:16]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("href") or row.get("url") or "")
        host = _safe_host(url)
        if not host or url in seen:
            continue
        seen.add(url)
        heading = str(row.get("title") or "").strip()[:300]
        snippet = str(row.get("body") or row.get("snippet") or "")[:900]
        is_exact = _heading_matches(local, heading)
        trusted = _is_trusted(host)
        context = bool(GAME_WORDS.search(heading + " " + snippet))
        collected.append(WebEvidence(heading, url, _source_group(host),
                                     is_exact, context, trusted))
    return tuple(collected)


def classify_game(
    title: str,
    *,
    code: str = "",
    dlsite_lookup: Callable[..., Detection] = detect_dlsite_game,
    web_search: Callable[[str], list[dict]] = default_web_search,
    max_variants: int = 2,
    allow_single_store_candidate: bool = False,
) -> SearchDecision:
    """온라인 검색 요청 1회에 대한 판별 결과. 저장·이름 변경은 절대 하지 않는다.

    1. DLsite 게임 확인 -> 통과
    2. DLsite 명백한 비게임 work_type -> 비게임 *추정* 별도 분류
    3. 미확인/후보/불명/접속 문제 -> 일반 인터넷 재검색
    4. 독립적이고 정확한 게임 출처 2곳 이상 확인하지 못하면 조회 불가 큐
    """
    display = _clean_input_title(title or "")
    try:
        first = dlsite_lookup(title, code=code, allow_title_search=True)
    except Exception as exc:
        first = Detection("lookup_unavailable", display,
                          reason=f"DLsite 조회 예외: {type(exc).__name__}")

    if first.status == "confirmed_game":
        return SearchDecision("confirmed_game", display,
                              proposed_title=first.work_title,
                              dlsite_status=first.status, dlsite_code=first.code,
                              reason="DLsite 등록 작품과 게임 유형을 확인했으므로 인터넷 재검색 없이 통과")
    if first.status == "registered_non_game":
        return SearchDecision("suspected_non_game", display,
                              proposed_title=first.work_title,
                              dlsite_status=first.status, dlsite_code=first.code,
                              reason="DLsite 작품 유형상 비게임으로 추정함. 수동 검토·변경 가능")
    if first.status == "input_error":
        return SearchDecision("input_error", display,
                              dlsite_status=first.status, reason=first.reason)
    if first.status not in {"registered_type_unknown", "needs_review", "unverified", "lookup_unavailable"}:
        return SearchDecision("lookup_unavailable", display,
                              dlsite_status=first.status, reason="지원하지 않는 판별 상태")

    # 로컬 원본 경로와 전체 압축파일 이름을 인터넷으로 전송하지 않는다.
    # 식별 가능한 작품명/품번만 전송. 등록된 작품명이 있으면 참고로 사용한다.
    # DLsite가 '다른 제목의 게임'을 반환했더라도 그 작품명으로 검색하면
    # 엉뚱한 게임을 확인 처리하게 된다. 로컬 제목이 있는 동안에는 로컬 우선.
    is_code_only = bool(re.fullmatch(r"(?:RJ|VJ|BJ|EJ)\d{6,8}", display.strip(), re.I))
    query_source = first.work_title if is_code_only and first.work_title else display
    queries = search_title_variants(query_source, limit=max(1, min(2, max_variants)))
    # 품번뿐인 파일명은 작품 코드 자체로 검색할 수 있다.
    if not queries and (first.code or code.strip()):
        queries = (first.code or code.strip(),)
    if not queries:
        return SearchDecision("lookup_unavailable", display, dlsite_status=first.status,
                              dlsite_code=first.code,
                              reason="검색할 작품명이나 코드가 없어 조회 불가", web_checked=False)
    all_evidence = []
    seen_urls = set()
    errors = []
    exact_game_sources = {}
    preferred_title = queries[0]
    for query in queries:
        try:
            hits = web_search(query) or []
            evidence = examine_web_results(query, hits)
        except Exception as exc:
            errors.append(type(exc).__name__)
            continue
        for row in evidence:
            if row.url not in seen_urls:
                seen_urls.add(row.url)
                all_evidence.append(row)
            if row.strong_match and (row.trusted_source or row.game_context):
                exact_game_sources[row.domain] = row
        if (len(exact_game_sources) >= 2
                and any(row.trusted_source for row in exact_game_sources.values())):
            # 검색 결과 제목·요약은 실제 판매 페이지의 진위 확인이 아니다.
            # 작품 페이지 원문 검증 전에는 확정 대신 후보로만 기록한다.
            return SearchDecision(
                "internet_candidate", display, proposed_title=preferred_title,
                dlsite_status=first.status, dlsite_code=first.code,
                reason="독립된 게임 관련 출처 2곳 이상에서 제목이 일치했습니다. "
                       "검색 결과만 확인했으므로 동일 작품인지 수동 또는 원문 검증이 필요합니다.",
                web_checked=True, evidence=tuple(all_evidence))
    if allow_single_store_candidate and all_evidence:
        # 공식 페이지 한 곳만 나와도 *제품 후보*는 보관한다. 사용자 파일과
        # 동일성 확인이나 '게임 확정'에는 사용하지 않는다.
        from .storefront_candidate import single_store_candidate
        source = single_store_candidate(display, all_evidence)
        if source:
            product_title, platform, url = source
            return SearchDecision(
                "internet_candidate", display, proposed_title=product_title,
                dlsite_status=first.status, dlsite_code=first.code,
                reason="공식 게임 스토어의 개별 작품 페이지 제목을 찾았습니다. "
                       "검색 결과만 확인했으므로 작품 원문/압축파일 동일성은 미검증입니다.",
                web_checked=True, evidence=tuple(all_evidence),
                source_platform=platform, source_url=url,
            )
    return SearchDecision(
        "lookup_unavailable", display, dlsite_status=first.status,
        dlsite_code=first.code, web_checked=True, evidence=tuple(all_evidence),
        reason=("일반 인터넷 검색 오류: " + ", ".join(errors) + ". " if errors else "")
               + "검색 후에도 게임 정체를 확정할 근거가 부족하여 조회 불가로 보관. 수동 분류 가능",
    )



def fast_classify_game(title: str, *, code: str = "") -> SearchDecision:
    """GUI 빠른 모드: 코드 직접 확인 + 일반 웹 요청 1회, 중복 DLsite 제목 검색 금지."""
    def lookup_fast(name: str, *, code: str = "",
                    allow_title_search: bool = False) -> Detection:
        # 작품 ID는 공식 등록 조회를 유지한다. ID 없는 제목에 대해서는
        # DLsite 제목 검색과 일반 웹 검색을 연달아 수행하지 않는다.
        return detect_dlsite_game(
            name, code=code, allow_title_search=False,
        )

    return classify_game(
        title, code=code, dlsite_lookup=lookup_fast,
        web_search=fast_web_search, max_variants=1,
        allow_single_store_candidate=True,
    )
