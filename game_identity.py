"""Identity-first, non-generative game artwork lookup helpers.

An archive basename is *not* evidence of the official game title.  Prefer an
explicitly matching public product ID, offer a text-only AI suggestion on user
request, and let the user review the title before fetching real image artwork.
Never rewrite original filenames or game metadata in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlsplit

from ai_providers import provider_details, _text_response, _extract_json
from online_artwork import suggest_query
from product_titles import extract_code, lookup_title, clean_title, PRODUCT_CODE


@dataclass(frozen=True)
class GameIdentity:
    title: str
    source: str
    code: str | None = None
    confidence: float = 0.0
    verified: bool = False


# Carefully cross-checked display aliases; other games are resolved from
# codes or publicly indexed records rather than guessed from loose words.
KNOWN_TITLE_CODES = {
    '6월의 너와 나': 'RJ01081508',
    '6月の君と僕': 'RJ01081508',
}


def find_public_work_code(title: str, searcher=None) -> str:
    """Find a possible code only with two independent title-bearing sources.

    This only produces a *candidate* code. The caller resolves the published
    metadata or requires manual user confirmation. One indexed search hit is
    insufficient evidence to bind the artwork of an unrelated title.
    """
    title = suggest_query(title)
    if len(title) < 3:
        raise LookupError('작품명 검색어가 너무 짧습니다.')
    if title.casefold() in {name.casefold() for name in KNOWN_TITLE_CODES}:
        return next(code for name, code in KNOWN_TITLE_CODES.items()
                    if name.casefold() == title.casefold())
    if searcher is None:
        from ddgs import DDGS
        with DDGS(timeout=12) as client:
            rows = list(client.text('"' + title + '" DLsite RJ', max_results=12) or [])
    else:
        rows = list(searcher(title) or [])
    by_code = defaultdict(set)
    normalized = ' '.join(title.casefold().split())
    for row in rows:
        if not isinstance(row, dict):
            continue
        page_title = str(row.get('title') or '')
        body = str(row.get('body') or row.get('snippet') or '')
        url = str(row.get('href') or row.get('url') or '')
        host = urlsplit(url).hostname or ''
        if not host or not normalized or normalized not in ' '.join((page_title + ' ' + body).casefold().split()):
            continue
        codes = {match.group(1).upper() for match in PRODUCT_CODE.finditer(page_title + ' ' + body + ' ' + url)}
        for code in codes:
            by_code[code].add(host.lower().removeprefix('www.'))
    confident = [code for code, hosts in by_code.items() if len(hosts) >= 2]
    if len(confident) != 1:
        raise LookupError('서로 다른 공개 출처에서 같은 작품 코드를 확인하지 못했습니다. 코드를 직접 입력해 주세요.')
    return confident[0]


def initial_identity(*names: str) -> GameIdentity:
    code = extract_code(*names)
    title = suggest_query(*names)
    if not code:
        code = next((product_code for alias, product_code in KNOWN_TITLE_CODES.items()
                     if title.casefold() == alias.casefold()), None)
    # A product code is more reliable than trying to infer a title from a
    # patch archive. The user can explicitly resolve the code next.
    if code and (not title or title.upper() == code):
        return GameIdentity(code, '작품 코드 발견 · 정식 작품명 확인 필요', code, 0.0, False)
    if not title:
        return GameIdentity('', '작품명 확인 필요', code, 0.0, False)
    label = '파일명에서 추출한 검색어 · 실제 작품명은 확인되지 않음'
    # A meaningful plain name is good enough to *search* for candidate images;
    # it is not automatically an official/verified identity.
    uncertain = bool(code) or bool(re.search(r'(?:patch|패치|mod|번역|수정)', title, re.I))
    return GameIdentity(title, label, code, 0.35 if uncertain else 0.65, False)


def lookup_code_identity(code: str, cache_path: Path) -> GameIdentity:
    title, source = lookup_title(code, cache_path)
    return GameIdentity(title, f'품번 일치 공개 작품정보: {source}', code, 1.0, True)


def suggest_ai_identity(filename: str, code: str | None, provider: str,
                        model: str, api_key: str) -> GameIdentity:
    """Opt-in text-only AI. This is NOT proof, and does not create images."""
    provider_details(provider)
    prompt = (
        'Identify the actual title of the VIDEO GAME or game work from this '
        'filename. Remove version/translation/release/patch notes. If a work '
        'code appears, do NOT invent a title or claim to have verified the code. '
        'If you are uncertain, return an empty title. Return ONLY JSON like '
        '{"title":"...","confidence":0.0}. Never include an artwork URL. '
        f'Filename: {filename!r}. Product code: {code or "none"}.'
    )
    text = _text_response(provider, model, prompt, api_key)
    try:
        result = _extract_json(text)
        title = clean_title(result.get('title', ''))
        confidence = float(result.get('confidence', 0.0))
        if not title or not 0.8 <= confidence <= 1.0:
            raise ValueError('AI가 게임 정체를 충분한 확신으로 식별하지 못했습니다.')
        # The suggested identity is still unverified; explicit user review.
        if len(title) > 150 or re.search(r'https?://|[\r\n]', title):
            raise ValueError('AI 응답의 작품명이 올바르지 않습니다.')
        return GameIdentity(title, f'{provider_details(provider)["name"]} 텍스트 AI 추천 · 미검증',
                            code, confidence, False)
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        raise LookupError('AI가 신뢰할 만한 작품명을 찾지 못했습니다. 직접 이름을 확인해 주세요.') from exc


def discover_public_identity(title: str, cache_path: Path, searcher=None) -> GameIdentity:
    """Public search -> independent-work-code comparison -> product record.

    If lookup fails, stop rather than presenting guessed artwork as genuine.
    """
    code = find_public_work_code(title, searcher=searcher)
    identity = lookup_code_identity(code, cache_path)
    return identity
