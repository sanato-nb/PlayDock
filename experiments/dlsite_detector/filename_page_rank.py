"""파일명 기반 웹 결과의 '게임 작품' 단위 평가.

검색 서비스 결과 제목에는 여러 사이트 제목이 합쳐질 수 있어 URL 구조와
게임명 일치를 우선 검증한다. 실제 압축파일 내부/사용자 경로는 보지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlsplit

POSSESSIVE = re.compile(r"(?i)(?<=\w)['’]s\b")
CHAPTER = re.compile(
    r"(?i)\b(?:chapter|chap|ch|episode|ep)\.?\s*[-_:#]?\s*(\d{1,3})\b"
)
GAME_CONTEXT = re.compile(
    r"(?i)\b(?:game|games|gameplay|gaming|visual novel|indie|rpg|"
    r"steam|itch\.io|dlsite|walkthrough|chapter|developer|download)\b"
    r"|게임|ゲーム|同人|게임정보"
)
BAD_PATH = (
    "/comments", "/comment/", "/discussion", "/forum/", "/collections/",
    "/profile", "/users/", "/tags/", "/search", "/community/", "/wiki/",
)
SUBPAGE = (
    "/devlog", "/posts/", "/purchase", "/download", "/updates/",
)
STOREFRONT_HOSTS = (
    "store.steampowered.com", "itch.io", "gamejolt.com",
)


def title_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = POSSESSIVE.sub("", text)
    return "".join(ch for ch in text if ch.isalnum())


def chapter_number(text: str) -> str:
    match = CHAPTER.search(unicodedata.normalize("NFKC", text or ""))
    return str(int(match.group(1))) if match else ""


def _word_exact(name: str, heading: str) -> bool:
    name = unicodedata.normalize("NFKC", name).strip()
    heading = unicodedata.normalize("NFKC", heading)
    return bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                          heading, flags=re.I))


def title_mentioned(local: str, heading: str) -> bool:
    """Elena's Story/elenastory 허용, Son of Nor/NOR 자동 동치 방지."""
    key = title_key(local)
    if len(key) < 3:
        return False
    if len(key) < 6:
        return _word_exact(local, heading)
    return key in title_key(heading)


def _page_slug(url: str) -> tuple[str, str, tuple[str, ...]]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    segments = tuple(unquote(s) for s in parsed.path.split("/") if s)
    if host == "store.steampowered.com" and len(segments) >= 2:
        if segments[0].casefold() == "app" and segments[1].isdigit():
            return "steam", segments[2] if len(segments) >= 3 else "", segments
        return "", "", segments
    if host.endswith(".itch.io"):
        return "itch", segments[0] if segments else "", segments
    if host == "gamejolt.com" or host.endswith(".gamejolt.com"):
        if len(segments) >= 2 and segments[0].casefold() == "games":
            return "gamejolt", segments[1], segments
    return "web", segments[-1] if segments else "", segments


def _slug_agrees(local: str, slug: str, heading: str, kind: str) -> bool:
    target = title_key(local)
    actual = title_key(slug)
    if not target or not actual:
        return False
    if target == actual:
        return True
    # 'Game Full', 'Game Demo'는 같은 작품 이름을 지닐 수 있지만
    # 버전/데모와 본편이 같다는 의미는 아니다.
    if len(target) >= 7 and actual.startswith(target):
        tail = actual[len(target):]
        if tail in {"full", "demo", "game", "windows", "pc", "beta", "alpha"}:
            return True
    # Elena's Story/elenastory처럼 소유격 -s가 URL에는 남고
    # 제목에만 아포스트로피로 표시된 경우에 한해 허용.
    if (kind == "itch" and len(target) >= 8 and title_mentioned(local, heading)
            and actual == target.replace("astory", "asstory")):
        return True
    return False


def _chapter_compatible(local_filename: str, heading: str, url: str) -> bool:
    required = chapter_number(local_filename)
    if not required:
        return True
    indicated = chapter_number(heading + " " + unquote(urlsplit(url).path)
                                .replace("-", " ").replace("_", " "))
    return not indicated or indicated == required


def page_score(local: str, heading: str, url: str, *,
               local_filename: str = "", snippet: str = "") -> int:
    """0이면 작품 후보 제외. 점수는 서열일 뿐, 게임 콘텐츠의 진위는 아님."""
    try:
        p = urlsplit(url)
        host = (p.hostname or "").casefold()
        if p.scheme != "https" or not host or p.username or p.password:
            return 0
        path = unquote(p.path).casefold()
        if any(x in path for x in BAD_PATH):
            return 0
        if not _chapter_compatible(local_filename, heading, url):
            return 0
        kind, slug, parts = _page_slug(url)
        exact_slug = _slug_agrees(local, slug, heading, kind)
        mentioned = title_mentioned(local, heading)
        if not (exact_slug or mentioned):
            return 0
        if kind == "itch":
            if not parts or not exact_slug:
                # 제작자 홈, 유사 제작자의 다른 게임은 모두 제외
                return 0
            if len(parts) == 1:
                return 110 if "demo" not in slug.casefold() else 65
            # 개발일지·구매·다운로드는 게임 홈이 아님: 단서만 유지.
            if any(s in path for s in ("/devlog", "/posts", "/updates")):
                return 25
            if "/purchase" in path or "/download" in path:
                return 75
            return 25
        if kind == "steam":
            # Steam URL slug가 제목과 다르면 Son of Nor != NOR.
            return 115 if exact_slug else 0
        if kind == "gamejolt":
            return 105 if exact_slug else 0
        if len(title_key(local)) < 5:
            # 단어가 짧은 일반 사이트는 오탐이 잦으므로 미확정
            # 단서 후보에서도 제외. 공식 작품 페이지는 위에서 허용.
            return 0
        context = bool(GAME_CONTEXT.search(heading + " " + snippet))
        if not (context or "kone.gg" in host or "mobygames.com" in host):
            return 0
        if exact_slug and mentioned:
            return 55
        if exact_slug:
            return 45
        if mentioned and context:
            return 30
        return 20 if mentioned else 0
    except (ValueError, TypeError):
        return 0


def steam_app_id(local: str, heading: str, url: str, *,
                 local_filename: str = "") -> str:
    """검색에 보인 실제 Steam 상품 URL이 정확히 게임명에 부합할 때만."""
    if page_score(local, heading, url, local_filename=local_filename) < 100:
        return ""
    parsed = urlsplit(url)
    if (parsed.hostname or "").casefold() != "store.steampowered.com":
        return ""
    match = re.match(r"^/app/([1-9]\d{2,9})(?:/|$)", parsed.path)
    return match.group(1) if match else ""
