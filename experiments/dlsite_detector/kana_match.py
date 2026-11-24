"""일본어 가나-로마자 정규화. 사전/유료 API 없이 '부분 발음 후보'만 판단.

일본어 전체 번역이나 한자의 독음을 추정하지 않는다. 시리즈 번호를 비교해
다른 시리즈 작품 오인도 막는다. 이 결과만으로 작품을 자동 확정하지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

_BASE = {
    "あ":"a","い":"i","う":"u","え":"e","お":"o",
    "か":"ka","き":"ki","く":"ku","け":"ke","こ":"ko",
    "さ":"sa","し":"shi","す":"su","せ":"se","そ":"so",
    "た":"ta","ち":"chi","つ":"tsu","て":"te","と":"to",
    "な":"na","に":"ni","ぬ":"nu","ね":"ne","の":"no",
    "は":"ha","ひ":"hi","ふ":"fu","へ":"he","ほ":"ho",
    "ま":"ma","み":"mi","む":"mu","め":"me","も":"mo",
    "や":"ya","ゆ":"yu","よ":"yo",
    "ら":"ra","り":"ri","る":"ru","れ":"re","ろ":"ro",
    "わ":"wa","を":"o","ん":"n",
    "が":"ga","ぎ":"gi","ぐ":"gu","げ":"ge","ご":"go",
    "ざ":"za","じ":"ji","ず":"zu","ぜ":"ze","ぞ":"zo",
    "だ":"da","ぢ":"ji","づ":"zu","で":"de","ど":"do",
    "ば":"ba","び":"bi","ぶ":"bu","べ":"be","ぼ":"bo",
    "ぱ":"pa","ぴ":"pi","ぷ":"pu","ぺ":"pe","ぽ":"po",
    "ぁ":"a","ぃ":"i","ぅ":"u","ぇ":"e","ぉ":"o",
}
_Y = {"き":"ky","し":"sh","ち":"ch","に":"ny","ひ":"hy","み":"my","り":"ry",
      "ぎ":"gy","じ":"j","ぢ":"j","び":"by","ぴ":"py"}
_SMALL_Y = {"ゃ":"a","ゅ":"u","ょ":"o"}
# 일본어 제목의 작가/서클명은 게임명의 일부로 비교하면 안 된다.
_TRAILING_CIRCLE = re.compile(r"\s*[\[【][^\]】]{1,90}[\]】]\s*$")
_ASCII_STEM = re.compile(r"^([a-z][a-z0-9]*?)(\d{1,3})?$")
_NUM = re.compile(r"(?<!\d)\d{1,3}(?!\d)")


def _hira(char: str) -> str:
    code = ord(char)
    return chr(code - 96) if 0x30A1 <= code <= 0x30F6 else char


@lru_cache(maxsize=4096)
def romanized_title(value: str) -> str:
    """가나/ASCII 문자만 로마자로 치환. 모르는 한자는 구분자로 남긴다."""
    original = unicodedata.normalize("NFKC", _TRAILING_CIRCLE.sub("", value))
    letters = [_hira(c) for c in original.casefold()]
    pieces: list[str] = []
    i = 0
    while i < len(letters):
        c = letters[i]
        if c == "っ" and i + 1 < len(letters):
            nxt = _BASE.get(letters[i + 1], "")
            if nxt:
                pieces.append(nxt[0])
            i += 1
            continue
        if i + 1 < len(letters) and c in _Y and letters[i + 1] in _SMALL_Y:
            pieces.append(_Y[c] + _SMALL_Y[letters[i + 1]])
            i += 2
            continue
        if c == "ー":
            # 장음은 로마자로 변환된 직전 모음 1회 반복.
            prev = "".join(pieces)
            if prev and prev[-1] in "aeiou":
                pieces.append(prev[-1])
        elif c in _BASE:
            pieces.append(_BASE[c])
        elif "a" <= c <= "z" or "0" <= c <= "9":
            pieces.append(c)
        else:
            pieces.append(" ")
        i += 1
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


def phonetic_score(query: str, official_title: str) -> int:
    """직접 제목 비교가 실패했을 때만 호출. 가나 발음+시리즈 번호 일치 → 후보 30.

    5자 이상 라틴 작품명만 사용. NOR/REC 등의 짧은 일반어와 숫자가 다른 시리즈는 제외.
    'BUZAMA 3' ↔ 'ブザマストリーマーズ -侮挫魔3-' 는 후보가 되지만
    'BUZAMA 2' ↔ 'ブザマストリーマーズ -侮挫魔3-' 는 제외한다.
    """
    q = re.sub(r"\s+", "", unicodedata.normalize("NFKC", query).casefold())
    m = _ASCII_STEM.fullmatch(q)
    if not m:
        return 0
    stem, series = m.groups()
    if len(stem) < 5 or stem in {"every", "other", "sample", "title", "games"}:
        return 0
    official = _TRAILING_CIRCLE.sub("", official_title)
    if not any("\u3040" <= c <= "\u30ff" for c in official):
        return 0
    roman = romanized_title(official)
    compact = re.sub(r"[^a-z0-9]", "", roman)
    if stem not in compact:
        return 0
    if series is not None:
        # 제목에 다른 시리즈 숫자만 있으면 절대 연결하지 않음.
        digits = _NUM.findall(unicodedata.normalize("NFKC", official))
        if series not in digits:
            return 0
    return 30
