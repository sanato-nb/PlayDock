"""v0.5: 공식 게임 판매 페이지 한 곳에서 발견된 후보를 *미확정*으로 보존.

일반 검색 결과의 스니펫이나 개발자 프로필은 작품 원문 검증을
대신하지 않는다. 실제 작품별 경로만 허용하며 수동 검토가 필수다.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from typing import Sequence

from .detector import normalized_title
from .pipeline import WebEvidence

POSSESSIVE = re.compile(r"(?i)(?<=\w)['’]s\b")
DEVLOG_TITLE = re.compile(r"\s[-–]\s(.{4,90}?)\sby\s[^|]{2,100}$", re.I)
ITCH_SUFFIX = re.compile(r"(?i)\s*[-–|]\s*itch\.io\s*$")
STEAM_SUFFIX = re.compile(r"(?i)\s*on Steam\s*$")


def _key(value: str) -> str:
    return normalized_title(POSSESSIVE.sub("", value))


def _headline_title(title: str, platform: str) -> str:
    if platform == "itch.io":
        match = DEVLOG_TITLE.search(title)
        if match:
            return match.group(1).strip()
        return ITCH_SUFFIX.sub("", title).strip()
    if platform == "steam":
        return STEAM_SUFFIX.sub("", title).strip()
    return title.strip()


def single_store_candidate(
    query: str, evidence: Sequence[WebEvidence],
) -> tuple[str, str, str] | None:
    """제목과 작품별 공식 URL이 부합하면 (title,platform,url)만 반환.

    검색 스니펫은 페이지 원문과 다른 작품일 수 있으므로 자동 확정 금지.
    """
    target = _key(query)
    if len(target) < 7:
        return None
    matches: dict[tuple[str, str], tuple[str, str, str]] = {}
    for hit in evidence:
        try:
            parsed = urlsplit(hit.url)
            host = (parsed.hostname or "").casefold()
            segments = [s for s in parsed.path.split("/") if s]
        except (ValueError, TypeError):
            continue
        platform = ""
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            continue
        if host.endswith(".itch.io") and len(segments) == 1:
            # 댓글·devlog·커뮤니티 하위 페이지는 실제 작품 홈이 아니다.
            if segments[0].casefold() in {"games", "profile", "collection", "posts", "comments", "devlog"}:
                continue
            platform = "itch.io"
        elif (host == "store.steampowered.com" and len(segments) in (2, 3)
              and segments[0] == "app" and segments[1].isdigit()):
            platform = "steam"
        if not platform:
            continue
        candidate = _headline_title(hit.title, platform)
        if _key(candidate) != target:
            continue
        key = (platform, _key(candidate))
        matches[key] = (candidate, platform, hit.url)
    if len(matches) != 1:
        return None
    return next(iter(matches.values()))
