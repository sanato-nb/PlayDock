"""게임명↔DLsite 공식 작품명 후보 분석.

검색 단계에서는 '후보 근거'를 보존하고, 최종 검증 단계에서만 작품을 평가.
외부 검색에 나온 RJ번호/문구만으로 같은 게임이라고 확정하지 않는다.
특히 시리즈 2 vs 20, 3 vs 2를 부분 문자열로 연결하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from difflib import SequenceMatcher

from .detector import normalized_title
from .kana_match import phonetic_score
from .search_terms import cleaned_search_title

_TRAILING_CREATOR = re.compile(r"\s*[\[【]([^\]】]{1,80})[\]】]\s*$")
_LATIN_TOKENS = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({"a", "the", "of", "and", "in", "on", "game", "dlsite", "rj"})
_NUMBER = re.compile(r"(?<![a-z0-9])(\d{1,3})(?![a-z0-9])")
_END_NUMBER = re.compile(r"(?:^|[\s._-])(\d{1,3})\s*$")
_TAIL_NUMBER = re.compile(r"(?<!\d)(\d{1,3})\s*[-~]?\s*$")


@dataclass(frozen=True)
class Evidence:
    score: int
    reason: str
    series_conflict: bool = False
    signals: tuple[str, ...] = ()


def _name(raw: str) -> str:
    return unicodedata.normalize("NFKC", cleaned_search_title(raw)).casefold().strip()


def _series_number(value: str) -> str:
    text = _TRAILING_CREATOR.sub("", _name(value)).rstrip(" -–—~　")
    # Works with "BUZAMA 3", "BUZAMA3", and "侮挫魔3"; not RJ serials.
    match = _TAIL_NUMBER.search(text)
    if match:
        number = match.group(1)
        if len(number) <= 3:
            return str(int(number))
    return ""


def _conflicts(query: str, candidate: str) -> bool:
    q = _series_number(query)
    if not q:
        return False
    # Reject only a clearly marked other title number; avoid year/metadata guesses.
    other = _series_number(candidate)
    if other and other != q:
        return True
    # For a multi-clause Japanese title, the number may be inside a suffix
    # rather than the very end (e.g. "-侮挫魔3- [circle]").
    if q and not other and re.search(r"[一-龯ぁ-ヿ]", candidate):
        official = _TRAILING_CREATOR.sub("", _name(candidate))
        visible = {str(int(n)) for n in _NUMBER.findall(official)}
        # No visible digits is not a contradiction: the Japanese title may
        # have kanji numerals, so leave it unconfirmed rather than reject.
        if visible and q not in visible:
            return True
    return False


def assess_title(query: str, official: str) -> Evidence:
    left, right = normalized_title(query), normalized_title(official)
    if not left or not right:
        return Evidence(0, "빈 제목")
    if _conflicts(query, official):
        return Evidence(0, "시리즈 번호 충돌", True, ("series_conflict",))
    if left == right:
        return Evidence(100, "정규화한 작품명 완전 일치", signals=("exact_title",))
    # A 2-digit title must not match 20 as a prefix. Series conflict above
    # handles an entire short/English title whose numerical suffix differs.
    if len(left) >= 7 or (len(left) >= 5 and any("가" <= c <= "힣" for c in left)):
        if left in right:
            return Evidence(65, "공식 제목에 게임명 전체가 포함됨", signals=("title_substring",))
    kana = phonetic_score(query, official)
    if kana:
        return Evidence(45, "가나 발음과 영문 제목이 유사함", signals=("kana_romanization",))
    a = [t for t in _LATIN_TOKENS.findall(_name(query))
         if len(t) >= 3 and t not in _STOPWORDS and not t.isdigit()]
    b = set(t for t in _LATIN_TOKENS.findall(_name(official))
            if len(t) >= 3 and t not in _STOPWORDS and not t.isdigit())
    # Two distinctive words are safer than matching "project" or "dungeon" alone.
    if len(set(a)) >= 2:
        overlap = len(set(a).intersection(b)) / len(set(a))
        if overlap >= 0.85:
            return Evidence(50, "서로 다른 두 개 이상의 작품명 단어 일치",
                            signals=("token_overlap",))
    # Fuzzy similarity is review-only, and only for reasonably long strings.
    if len(left) >= 9 and len(right) >= 9:
        ratio = SequenceMatcher(None, left, right).ratio()
        if ratio >= 0.91:
            return Evidence(30, "철자 유사 (수동 확인 필수)", signals=("fuzzy",))
    return Evidence(0, "작품명·발음·시리즈의 연결 근거 부족")


def assess_many(names, candidate: str) -> Evidence:
    checks = [assess_title(name, candidate) for name in names]
    if not checks:
        return Evidence(0, "검색 이름 없음")
    # Some local archives bundle multiple titles; a conflicting single variant
    # must not veto a separately stated matching different title.
    return max(checks, key=lambda e: e.score)
