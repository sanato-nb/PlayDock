"""파일명에 실제 존재하는 한국어/영어/일본어 표기와 웹에서 명시된 원제를 다루는 도구.

임의의 번역문을 작품의 일본어 정식명처럼 생성하지 않는다.
번역명과 웹 원제의 연결은 품번의 자동 확정 근거로 사용하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata

from .search_terms import cleaned_search_title, title_web_queries

PARENS = re.compile(r"\(([^()]{3,100})\)")
EXTRA_NOTES = re.compile(
    r"\[([^\]]{1,100})\]"
)
DROP_NOTE = re.compile(
    r"(?i)(?:\b(?:fix|rev|patch|mod|dlc|build|update|beta|alpha)\b"
    r"|음성판|추가\s*번역|검수|수정|본편|노모|플랫폼|폰트|\d{4}[-.]\d\d[-.]\d\d)"
)
JA = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
HAS_HANGUL = re.compile(r"[\uac00-\ud7a3]")
HAS_LATIN = re.compile(r"[A-Za-z]")
ORIGINAL_LABEL = re.compile(
    r"(?:원제|일본어\s*(?:원제|제목|명)|原題|日本語(?:の)?タイトル"
    r"|Japanese\s+(?:title|name)|Original\s+title|日文(?:名|标题)|原名)"
    r"\s*[:：=\-]\s*[「『“\"']?"
    r"([^\n\r「『」』“\"'|,，;；]{3,95})",
    re.I,
)
STOP_AT = re.compile(r"\s(?:[-–—]\s|(?:DLsite|RJ\d{6,8}|Download|게임\s*소개)\b)", re.I)
MAX_WEB_TITLES = 3


def _key(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def _append(out: list[str], seen: set[str], value: str) -> None:
    val = re.sub(r"\s+", " ", value).strip(" \t\r\n-_.:：()[]")
    ident = _key(val)
    if 2 <= len(val) <= 160 and len(ident) >= 2 and ident not in seen:
        out.append(val)
        seen.add(ident)


def title_candidates(raw: str, *, limit: int = MAX_WEB_TITLES) -> tuple[str, ...]:
    """병기된 이름 → 각 언어 단독 이름 → 전체 이름. 요청 건수는 최대 3개."""
    clean = cleaned_search_title(raw)
    if not clean:
        return ()
    clean = EXTRA_NOTES.sub(
        lambda m: " " if DROP_NOTE.search(m.group(1)) else m.group(0), clean
    )
    clean = re.sub(r"\s+", " ", clean).strip()
    out: list[str] = []
    seen: set[str] = set()

    for part in PARENS.findall(clean):
        if (HAS_LATIN.search(part) or JA.search(part)) and (
            not DROP_NOTE.search(part)
        ):
            _append(out, seen, part)

    without_parens = PARENS.sub(" ", clean).strip()
    # +로 결합한 합본은 개별 작품명을 먼저 찾는다. 같은 작품이라고 단정하지 않는다.
    split_titles = [x.strip() for x in re.split(r"\s+\+\s+", without_parens)]
    if len(split_titles) > 1:
        for title in split_titles[:2]:
            _append(out, seen, title)
    else:
        _append(out, seen, without_parens)

    # 일본어+한글 병기 문자열은 단독 표기가 이미 있으면 우선 사용한다.
    # 파일명에 존재하지 않는 일본어 번역을 만들어내지 않는다.
    _append(out, seen, clean)
    if not out:
        for name in title_web_queries(raw):
            _append(out, seen, name)
    return tuple(out[:max(1, min(limit, MAX_WEB_TITLES))])


def explicit_original_titles(rows: list[dict], trusted_names: tuple[str, ...],
                             *, limit: int = 2) -> tuple[str, ...]:
    """관련 웹 검색 결과에서 *명시적으로 원제라고 표기된* 일본어 제목만 수집.

    검색 결과는 독립적인 증거가 아니므로 공식 확인과 자동 동일작품 확정은 금지.
    """
    out: list[str] = []
    seen = {_key(q) for q in trusted_names}
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        heading = str(row.get("title") or "")[:240]
        snippet = str(row.get("body") or "")[:420]
        text = heading + " " + snippet
        compact = _key(text)
        # 한국어 제목 또는 이미 알려진 영어 별칭이 표시된 결과만 사용.
        if not any(len(_key(name)) >= 5 and _key(name) in compact
                   for name in trusted_names):
            continue
        for match in ORIGINAL_LABEL.finditer(text):
            candidate = STOP_AT.split(match.group(1), maxsplit=1)[0]
            candidate = candidate.strip(" .:：/、。)）]】」』")
            # 완전한 원제인지 불분명한 단일 글자/기호/단순 번역 라벨 배제
            if (len(JA.findall(candidate)) < 2 or
                candidate.startswith(("日本語", "原題")) or
                len(candidate) > 85):
                continue
            _append(out, seen, candidate)
            if len(out) >= limit:
                return tuple(out)
    return tuple(out)
