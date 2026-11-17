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
    r"|한글(?:패치|화)?|한국어(?:패치|번역)?|번역(?:패치|판)?"
    r"|korean\s*(?:patch|translation)?|eng(?:lish)?\s*patch"
    r"|machine\s*translation|uncensored|patch(?:ed)?|dlsite"
    r"|(?:RJ|VJ|BJ|EJ)\d{6,8}"
    r")\s*(?:\]|\)|】)",
    re.I,
)
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
    candidates = (clean, original)
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
