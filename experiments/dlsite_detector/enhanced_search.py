"""AI 없이 Steam 상품 원본 확인, 명시적 별칭 재검색, 파일 종류를 결합한다.

DLsite/일반 웹 검색 코드는 그대로 재사용하고, 앱 본체/DB/UI를 import하지 않는다.
인터넷 검색 결과와 공식 Steam 원본 상품을 구별한다.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable
from urllib.parse import urlsplit
import re

from .detector import normalized_title
from .identity_hints import extract_hints
from .pipeline import SearchDecision, classify_game
from .search_terms import cleaned_search_title
from .steam_client import SteamProduct, fetch_steam_product, SteamLookupUnavailable


STEAM_PAGE = re.compile(r"^/app/([1-9]\d{2,9})(?:/|$)")
FILE_ONLY = frozenset({
    "patch_candidate", "dlc_candidate", "server_package_candidate",
    "modpack_candidate", "bundle_candidate", "game_with_patch_candidate",
})


def _steam_url_id(url: str) -> str:
    """Steam 도메인 위장과 아이디 아닌 링크는 검증하지 않는다."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https"
                or (parsed.hostname or "").lower() != "store.steampowered.com"
                or parsed.username or parsed.password):
            return ""
        match = STEAM_PAGE.match(parsed.path)
        return match.group(1) if match else ""
    except (ValueError, TypeError):
        return ""


def _matches(product_title: str, requested_name: str, aliases: tuple[str, ...]) -> bool:
    wanted = normalized_title(requested_name)
    actual = normalized_title(product_title)
    return bool(actual and (actual == wanted or actual in {
        normalized_title(alias) for alias in aliases
    }))


def enhanced_classify_game(
    title: str,
    *,
    code: str = "",
    classifier: Callable[..., SearchDecision] = classify_game,
    steam_fetcher: Callable[[str], SteamProduct | None] = fetch_steam_product,
) -> SearchDecision:
    """압축파일명 1차 검색의 고도화 판별 결과.

    Steam ID → 원본 상품 API 확인, 그 외 DLsite→웹 조회. 일반 검색 결과에
    Steam 작품 페이지가 있으면 원본 App ID를 다시 조회하고, 명시적으로
    병기된 제목의 별칭은 마지막 수단으로 한 번만 재검색한다.

    검색 결과는 작품 존재 증거이며 압축파일 자체와 동일하다는 보장은 없다.
    """
    hints = extract_hints(title)
    kind = hints.archive_kind
    request_name = cleaned_search_title(title)
    if len(hints.steam_app_ids) > 1:
        return SearchDecision(
            "internet_candidate", title, dlsite_code=(hints.dlsite_codes[0] if hints.dlsite_codes else ""),
            source_platform="steam", archive_kind=kind,
            reason="Steam App ID가 여러 개라 단일 작품으로 자동 연결하지 않습니다.",
        )

    store_error = ""
    if hints.steam_app_ids:
        sid = hints.steam_app_ids[0]
        try:
            item = steam_fetcher(sid)
        except (SteamLookupUnavailable, OSError, TimeoutError, ValueError) as exc:
            store_error = type(exc).__name__
            item = None
        if item and item.app_id == sid:
            match = _matches(item.title, request_name, hints.title_aliases)
            if item.item_type == "game" and match and kind not in FILE_ONLY:
                return SearchDecision(
                    "platform_confirmed_game", title,
                    proposed_title=item.title, source_platform="steam",
                    source_id=sid, source_url=item.url, archive_kind=kind,
                    reason="Steam App ID와 공식 상품명·게임 유형이 일치합니다. "
                           "로컬 압축파일의 실제 내용까지 검증한 것은 아닙니다.",
                )
            # DLC/사운드트랙/서버팩 등은 게임 본편으로 자동 지정 금지.
            # DLsite 코드가 함께 있을 때는 해당 코드의 확인도 계속 시도한다.
            if not hints.dlsite_codes:
                return SearchDecision(
                    "internet_candidate", title, proposed_title=item.title,
                    source_platform="steam", source_id=sid, source_url=item.url,
                    archive_kind=kind,
                    reason="Steam 상품 원본을 찾았지만 "
                           + ("게임 이름이 다릅니다." if not match else
                              "게임 본편과 다른 상품 유형 또는 파일 구성이 의심됩니다.")
                           + " 수동 확인이 필요합니다.",
                )

    original = classifier(title, code=code)
    original = replace(original, archive_kind=kind)
    if original.status in {"confirmed_game", "suspected_non_game", "platform_confirmed_game", "input_error"}:
        if original.status == "confirmed_game" and kind in FILE_ONLY:
            return replace(
                original, status="internet_candidate",
                reason="DLsite 작품은 확인됐지만 이 압축파일은 " + kind
                       + " 유형으로 보여 본편이라고 단정할 수 없습니다.",
            )
        return original

    # 검색 결과가 Steam 링크를 보여주더라도 검색 스니펫은 검증 근거가 아니다.
    # 허용된 Steam 도메인의 App ID를 공식 JSON으로 한 번 더 확인한다.
    tried = set(hints.steam_app_ids)
    for row in original.evidence:
        sid = _steam_url_id(row.url)
        if not sid or sid in tried:
            continue
        tried.add(sid)
        if len(tried) > 4:
            break
        try:
            item = steam_fetcher(sid)
        except (SteamLookupUnavailable, OSError, TimeoutError, ValueError):
            continue
        if item is None or item.app_id != sid or item.item_type != "game":
            continue
        if not _matches(item.title, request_name, hints.title_aliases):
            continue
        # 파일명으로 찾은 공식 Steam 게임은 '게임 존재'의 강한 근거지만,
        # 다운로드 파일의 정체까지는 증명하지 못하므로 수동 확인으로 남긴다.
        return replace(
            original, status="internet_candidate", proposed_title=item.title,
            source_platform="steam", source_id=sid, source_url=item.url,
            reason="Steam 상품 원본에서 제목·게임 유형을 확인했습니다. "
                   "로컬 압축파일과 동일한지는 사용자 검증이 필요합니다.",
        )

    # 파일명에 사용자가 직접 병기한 공식 후보 별칭만 활용한다.
    # 번역/음역은 AI로 만들어내지 않으며 아무 영문 단어를 다른 언어로 바꾸지 않는다.
    for alias in hints.title_aliases[:2]:
        if not alias or normalized_title(alias) == normalized_title(request_name):
            continue
        second = classifier(alias, code="")
        if second.status in {"confirmed_game", "platform_confirmed_game",
                             "internet_confirmed_game", "internet_candidate"}:
            return replace(
                second, status="internet_candidate",
                original_query=title, archive_kind=kind,
                reason="파일명에 병기된 별칭 '" + alias[:80]
                       + "'으로 작품을 찾았습니다. 해당 파일과 동일 작품인지 확인이 필요합니다.",
            )

    if store_error:
        return replace(original,
                       reason=original.reason + " Steam 원본 조회 실패: " + store_error)
    return original
