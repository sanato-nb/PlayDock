"""게임 압축파일 이름에서 검색어를 만드는 독립 공통 모듈.

원본 이름은 변경하지 않는다. 시리즈 번호(2, III, Episode 3 등)는 보존하고
작품 번호/버전/일반적인 번역 패치·배포 태그만 검색 단계에서 제외한다.
"""
from __future__ import annotations

import re
import unicodedata


CODE = re.compile(r"(?<![A-Za-z0-9])(?:RJ|VJ|BJ|EJ)\d{6,8}(?![A-Za-z0-9])", re.I)
ARCHIVE = re.compile(r"\.(?:zip|rar|7z)$", re.I)
# 파일 뒤의 명시적 버전만 제거. 'Game 2'를 버전으로 오인하지 않는다.
VERSION_SUFFIX = re.compile(
    r"(?:[\s_.-]+)(?:v(?:er(?:sion)?)?\.?\s*)\d+(?:[._]\d+){0,5}"
    r"(?:[\s_-]*(?:patch\d*|hotfix\d*|final))?$",
    re.I,
)
# 특정 괄호 태그가 검색을 방해할 때만 삭제한다. 임의의 괄호 속 부제는 유지.
DROP_TAG = re.compile(
    r"(?:\[|\(|【)\s*(?:"
    r"(?:v(?:er(?:sion)?)?\.?\s*)?\d+(?:[._]\d+){1,5}\s*(?:patch|hotfix)?"
    r"|(?:v(?:er(?:sion)?)?\.?\s*)\d+(?:[._]\d+){0,5}"
    r"|한글\s*(?:패치|화)?|한국어\s*(?:패치|번역)?|번역\s*(?:패치|판)?"
    r"|korean\s*(?:patch|translation)?|eng(?:lish)?\s*patch"
    r"|machine\s*translation|uncensored|patch(?:ed)?|dlsite"
    r"|(?:RJ|VJ|BJ|EJ)\d{6,8}"
    r")\s*(?:\]|\)|】)",
    re.I,
)
# 플랫폼 식별자·배포 속성은 검색어에서 제거하되, 실제 분류는 별도 저장한다.
DISTRIBUTION_TAG = re.compile(
    r"\[\s*(?:Steam\s*(?:app\s*(?:id)?|id)?\s*[:#=-]?\s*\d{3,10}"
    r"|(?:RJ|VJ|BJ|EJ)\d{6,8}\s*[·,;/]\s*Steam\s*\d{3,10}"
    r"|Server(?:\s+v[\d.]+)?|PC|PC\s*본편|itch\.io\s*Windows"
    r"|DLC\s*[\d._\s]+|한국어\s*패치(?:\s*Fix\d+)?"
    r"|Update\s*\d+)"
    r"\s*\]",
    re.I,
)
# 번역/패치/출시 버전/리팩 등 명백한 배포 메모만 제거한다.
# 게임 부제일 수 있는 임의의 [내용]은 제거하지 않는다.
BRACKET_METADATA = re.compile(r"\[([^\]]{1,120})\]")
META_TAG = re.compile(
    r"(?i)(?:"
    r"한국어|한글|번역|노모|모자이크|검수|기번|손번역|기계|이미지\s*번역"
    r"|\b(?:fix|patch|beta|alpha|hotfix|update|dlc|mod|uncensor(?:ed)?)\b"
    r"|공식\s*한국어|신버전|리텍|팅김\s*버그|최신\s*버전"
    r"|\b(?:chap(?:ter)?|episode)\.?\s*\d+\b"
    r")"
)
DATE_TAG = re.compile(r"^(?:\d{6,8}|\d{4}-\d{2}-\d{2})$")
VERSION_NOTE = re.compile(r"(?i)^v\d+(?:[._]\d+)*\s*(?:fix|patch|hotfix)?$")

def _drop_known_metadata(match: re.Match[str]) -> str:
    note = match.group(1).strip()
    if META_TAG.search(note) or DATE_TAG.fullmatch(note) or VERSION_NOTE.fullmatch(note):
        return " "
    return match.group(0)


SPACES = re.compile(r"\s+")


def archive_basename(raw: str) -> str:
    """경로가 주어져도 네트워크 검색어에 절대 포함시키지 않는다."""
    if not isinstance(raw, str):
        return ""
    basename = re.split(r"[/\\]", raw)[-1].strip()
    return ARCHIVE.sub("", basename)


def cleaned_search_title(raw: str) -> str:
    """검색 전용 이름. 원본 파일/DB에는 손대지 않는다."""
    title = unicodedata.normalize("NFKC", archive_basename(raw))
    title = DROP_TAG.sub(" ", title)
    title = DISTRIBUTION_TAG.sub(" ", title)
    title = BRACKET_METADATA.sub(_drop_known_metadata, title)
    title = CODE.sub(" ", title)
    title = VERSION_SUFFIX.sub("", title).strip()
    # _ 는 배포 파일명에서 흔한 단어 구분자. 마침표는 제목/시리즈 표기일 수 있어 유지.
    title = title.replace("_", " ")
    title = SPACES.sub(" ", title).strip(" -_.")
    return title[:180]


def search_title_variants(raw: str, *, limit: int = 2) -> tuple[str, ...]:
    """정리한 게임명 우선, 실패 시 원본 파일명 재검색. 중복과 빈 제목 제외."""
    original = unicodedata.normalize("NFKC", archive_basename(raw))
    clean = cleaned_search_title(raw)
    # RJ/VJ/BJ/EJ 코드가 섞인 원본 이름은 일반 웹 재검색에 불필요한
    # 잡음을 보태므로, 정리한 제목이 있다면 원본 재시도를 생략한다.
    candidates = (clean,) if clean and CODE.search(original) else (clean, original)
    found = []
    seen = set()
    for value in candidates:
        key = value.casefold().strip()
        if not key or key in seen or not any(ch.isalpha() for ch in value):
            continue
        seen.add(key)
        found.append(value)
        if len(found) >= limit:
            break
    return tuple(found)


# 품번이 없는 압축파일 전용: 번역명 외에도 파일명에 병기된 원제/영문명을 검색한다.
# 자동 기계번역으로 작품명을 지어내지 않고 이미 존재하는 별칭만 사용.
ALIASED_TITLE = re.compile(r"\\(([^()]{4,90})\\)")
WEB_JUNK = re.compile(r"(?i)\\b(?:RJ|VJ|BJ|EJ)\\d{6,8}\\b")


def title_web_queries(raw: str, *, limit: int = 2) -> tuple[str, ...]:
    """제목명 검색 쿼리 후보. 공백·괄호 정리, 로컬 경로 제거, 별칭 우선.
    
    - 원래 작품명이 일본어·영어로 병기되어 있으면 독립 쿼리로 검색.
    - 한국어 제목을 일본어로 임의 번역하지는 않는다.
    - 과다 요청 방지를 위해 최대 2개만 만든다.
    """
    clean = cleaned_search_title(raw)
    if not clean:
        return ()
    names = []
    # '한국어 제목 (English Title)' -> 영어 별칭과 전체 제목을 모두 시도.
    for inside in ALIASED_TITLE.findall(clean):
        term = inside.strip(" -_")
        if re.search(r"[A-Za-z]{3}", term) and not WEB_JUNK.search(term):
            names.append(term)
    names.append(clean)
    unique = []
    seen = set()
    for name in names:
        name = SPACES.sub(" ", name).strip()
        ident = name.casefold()
        if ident and ident not in seen and len(name) >= 2:
            unique.append(name[:160])
            seen.add(ident)
        if len(unique) >= max(1, min(limit, 3)):
            break
    return tuple(unique)
