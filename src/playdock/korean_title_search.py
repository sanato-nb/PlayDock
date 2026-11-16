"""Search for *existing* Korean game titles on public web pages.

This is NOT machine translation. Search hits are only unverified suggestions:
users must review a page, optionally correct the candidate, and explicitly save
before any library metadata changes. Never download executable/game content.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import ipaddress
import re
from urllib.parse import urlsplit

from product_titles import PRODUCT_CODE, clean_title

HANGUL = re.compile(r'[가-힣]')
REMOVE_TAGS = re.compile(r'<[^>]+>')
COMMON_CATEGORIES = re.compile(
    r'(?i)^(?:검색\s*결과|한국어\s*검색\s*결과|상품\s*정보|작품\s*정보|한국어\s*(?:제목|작품명)|'
    r'다운로드|한글\s*패치|번역\s*자료|리뷰|이용\s*후기|무료|모음|게임\s*목록|'
    r'판매\s*페이지|공식\s*사이트|코드\s*검색|작품명\s*조회)$'
)
LABELS = re.compile(r'(?i)\s*[\[(](?:한글판|한국어판|리뷰|후기|다운로드|무료|RJ\d{6,8})[\])]\s*')


@dataclass(frozen=True)
class KoreanTitleHit:
    title: str               # May need manual correction; not verified.
    url: str                 # Source page to inspect.
    page_title: str          # Raw search result heading.
    excerpt: str             # Search snippet, never assumed authoritative.
    matched_code: bool      # Search result explicitly mentions the work ID.


def _safe_source(url: object) -> str | None:
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
                or host in {'localhost', '127.0.0.1', '0.0.0.0'}
                or host.endswith(('.local', '.internal', '.localhost'))):
            return None
        if parsed.port not in (None, 443):
            return None
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return None
        except ValueError:
            pass
    except ValueError:
        return None
    return url


def _plain(value: object, limit: int = 350) -> str:
    raw = str(value or '')[:limit * 2]
    return re.sub(r'\s+', ' ', unescape(REMOVE_TAGS.sub(' ', raw))).strip()[:limit]


def suggest_korean_heading(page_title: str, code: str | None) -> str | None:
    """Extract only an existing Korean heading, never translate Japanese.

    This is intentionally conservative. A site-search title is not proof of
    the official Korean name; the user always confirms or edits it.
    """
    title = _plain(page_title, 240)
    if not title:
        return None
    # Site names tend to appear after a divider; preserve punctuation inside
    # the work title, such as '사랑 - 그리고 우리' only when no clean alternative.
    parts = re.split(r'\s+[|｜–—]\s+|\s+-\s+(?=[^\-]{2,35}$)', title)
    options = []
    for part in parts:
        if code:
            part = re.sub(r'(?<![A-Za-z0-9])' + re.escape(code) + r'(?!\d)', ' ', part, flags=re.I)
        part = LABELS.sub(' ', part)
        part = re.sub(r'\s+', ' ', part).strip(' [](){}|·:;,.\u200b')
        if (HANGUL.search(part) and 2 <= len(part) <= 110 and clean_title(part)
                and not COMMON_CATEGORIES.fullmatch(part)):
            # Prefer a concrete work name over a generic category/SEO caption.
            score = 10 - int(bool(re.search(r'다운로드|리뷰|모음|검색|결과|후기|자료|무료', part))) * 12
            score -= len(part) / 200
            options.append((score, part))
    return max(options, default=(None, None))[1]


def _default_search(query: str) -> list[dict]:
    from ddgs import DDGS
    with DDGS(timeout=12) as ddgs:
        return list(ddgs.text(query, region='kr-kr', safesearch='moderate', max_results=9) or [])


def find_korean_titles(code: str | None, original_title: str = '', *, searcher=None,
                       limit: int = 12) -> list[KoreanTitleHit]:
    """Search Korean-language public pages for a specific work.

    With an RJ/VJ/BJ/EJ code, candidates MUST include that exact identifier
    in the result. Without one, a recognizable full original title must occur
    in the result. A candidate is never applied automatically.
    """
    code = (code or '').strip().upper() or None
    if code and not PRODUCT_CODE.fullmatch(code):
        raise ValueError('올바른 작품 코드(RJ/VJ/BJ/EJ)를 입력하세요.')
    original = _plain(original_title, 120)
    # A code-only label is not useful as an additional name-based query.
    meaningful_original = original if (len(original) >= 4 and
        not PRODUCT_CODE.fullmatch(original) and not re.fullmatch(
        r'(?:RJ|VJ|BJ|EJ)\d{6,8}(?:\s*\[[^]]+\])*', original, re.I)) else ''
    if not code and not meaningful_original:
        raise ValueError('작품 코드나 검색 가능한 게임명을 입력해 주세요.')
    if not 1 <= limit <= 30:
        raise ValueError('검색 결과 개수가 잘못되었습니다.')
    queries = ([f'"{code}" 한국어 게임 제목', f'"{code}" 한글 작품명'] if code else [])
    if meaningful_original:
        queries.append(f'"{meaningful_original}" 한국어 게임 제목' + (f' "{code}"' if code else ''))
    search = searcher or _default_search
    hits: list[KoreanTitleHit] = []
    seen = set()
    succeeded = False
    for query in queries:
        try:
            rows = search(query)
            succeeded = True
        except Exception:
            continue
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            url = _safe_source(row.get('href') or row.get('url') or row.get('link'))
            if not url or url in seen:
                continue
            page_title = _plain(row.get('title'), 240)
            excerpt = _plain(row.get('body') or row.get('snippet'), 350)
            evidence = ' '.join([page_title, excerpt, url])
            exact_code = bool(code and re.search(r'(?<![A-Za-z0-9])' + re.escape(code)
                              + r'(?!\d)', evidence, re.I))
            if code and not exact_code:
                continue
            if not code and meaningful_original.casefold() not in evidence.casefold():
                continue
            candidate = suggest_korean_heading(page_title, code)
            if candidate is None:
                continue
            # A search engine can show results listing multiple products.
            # Keep them as unverified suggestions for user selection only.
            seen.add(url)
            hits.append(KoreanTitleHit(candidate, url, page_title, excerpt, exact_code))
            if len(hits) >= limit:
                return hits
    if not succeeded:
        raise LookupError('웹 검색 서비스에 연결하지 못했습니다. 네트워크 연결 또는 검색 제한을 확인해 주세요.')
    return hits
