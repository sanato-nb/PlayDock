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

    @property
    def label(self) -> str:
        return {
            "confirmed_game": "DLsite 게임 확인 · 통과",
            "suspected_non_game": "비게임으로 추정 · 별도 분류",
            "internet_confirmed_game": "인터넷 검색으로 게임 확인",
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
    """사용자가 온라인 조회를 요청한 경우에만 실행되는 검색 연결기."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("일반 인터넷 검색에 ddgs 패키지가 필요합니다.") from exc
    with DDGS(timeout=12) as client:
        return list(client.text(f'"{query}" game', max_results=12) or [])


def examine_web_results(query: str, records: list[dict]) -> tuple[WebEvidence, ...]:
    local = normalized_title(query)
    seen = set()
    collected = []
    for row in records[:12]:
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
    query = first.work_title or display
    query = re.sub(r"\[(?:RJ|VJ|BJ|EJ)\d{6,8}\]", "", query, flags=re.I).strip()
    if not normalized_title(query):
        query = first.code or code.strip()
    if not query:
        return SearchDecision("lookup_unavailable", display, dlsite_status=first.status,
                              dlsite_code=first.code,
                              reason="검색할 작품명이나 코드가 없어 조회 불가", web_checked=False)
    try:
        hits = web_search(query) or []
        evidence = examine_web_results(query, hits)
    except Exception as exc:
        return SearchDecision("lookup_unavailable", display, dlsite_status=first.status,
                              dlsite_code=first.code, web_checked=True,
                              reason=f"일반 인터넷 검색 실패: {type(exc).__name__}")
    # 독립 출처 최소 2개 + 그중 하나는 알려진 게임 플랫폼/DB인 경우에만 자동 확정.
    exact_game_sources = {
        row.domain: row for row in evidence
        if row.strong_match and (row.trusted_source or row.game_context)
    }
    if (len(exact_game_sources) >= 2
            and any(row.trusted_source for row in exact_game_sources.values())):
        return SearchDecision(
            "internet_confirmed_game", display, proposed_title=query,
            dlsite_status=first.status, dlsite_code=first.code,
            reason="같은 작품명과 게임 문맥이 확인된 독립 출처 2곳 이상을 대조함",
            web_checked=True, evidence=evidence)
    return SearchDecision(
        "lookup_unavailable", display, dlsite_status=first.status,
        dlsite_code=first.code, web_checked=True, evidence=evidence,
        reason="인터넷 검색 후에도 게임 정체를 확정할 근거가 부족하여 조회 불가로 보관. 수동 분류 가능",
    )
