"""비영어권 배포명에서 영어 원제 *후보*를 보수적으로 찾는다.

정확한 제목 검색이 실패한 경우에 한해 이미 수집한 웹 검색 결과 제목을
재사용한다. 웹 문장에 원제를 나란히 적어둔 독립 도메인 2곳 이상이
동일한 영문 제목을 가리킬 때만 미검증 후보로 제공한다.

이 모듈은 영문 원제를 만들어내거나 공식 등록/동일성 확인을 하지 않는다.
"""
from __future__ import annotations

import re

from .pipeline import WebEvidence
from .search_terms import cleaned_search_title

# 단어 사이의 공백이 있는 2~6단어 영문 고유명사를 후보로 간주한다.
LATIN_TITLE = re.compile(
    r"(?<![A-Za-z])[A-Z][a-zA-Z']{2,}(?:\s+[A-Z][a-zA-Z']{2,}){1,5}(?![a-zA-Z])"
)
IGNORE_WORDS = frozenset({
    "Steam", "DLsite", "DLC", "Game", "Games", "Korean", "English",
    "Patch", "Download", "Free", "Latest", "Update", "Windows",
    "Original", "Version", "Ver", "Play", "Review", "Demo", "Full",
    "ASMR", "RPG", "Maker", "Unity", "Online", "Official",
})


def _has_non_latin_title(title: str) -> bool:
    return any(
        ('가' <= ch <= '힣') or ('ぁ' <= ch <= 'ゟ')
        or ('ァ' <= ch <= 'ヿ') or ('一' <= ch <= '鿿')
        for ch in title
    )


def discover_parallel_title(
    original_title: str, evidence: tuple[WebEvidence, ...],
) -> tuple[str, tuple[str, ...]] | None:
    """동일 게시물 도메인 중복 제외. 원제 후보와 근거 도메인 반환.

    비공식 자료에 두 언어가 나란히 적혀 있을 뿐이므로 검색 후보만
    반환한다. 원본 게임이나 구매 페이지의 동일성은 증명하지 않는다.
    """
    wanted = cleaned_search_title(original_title).casefold()
    if not wanted or len(wanted) < 3 or not _has_non_latin_title(wanted):
        return None
    hosts: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for hit in evidence[:32]:
        heading = hit.title.strip()
        # 검색한 한국어/일본어 이름과 영문 이름이 '같은' 결과 제목에
        # 함께 적혀 있어야 한다. 관련 없는 스니펫 문구에서는 추출 금지.
        if wanted not in heading.casefold():
            continue
        for match in LATIN_TITLE.finditer(heading):
            title = match.group(0).strip()
            words = title.split()
            if any(word.casefold() in {v.casefold() for v in IGNORE_WORDS}
                   for word in words):
                continue
            if len(title) > 90 or len(title) < 7:
                continue
            key = title.casefold()
            hosts.setdefault(key, set()).add(hit.domain.casefold())
            labels.setdefault(key, title)
    # 독립 도메인 2곳 이상에서 *같은* 표현을 발견했을 때만 제공.
    matched = [(name, domains) for name, domains in hosts.items() if len(domains) >= 2]
    if len(matched) != 1:
        return None
    name, domains = matched[0]
    return labels[name], tuple(sorted(domains))
