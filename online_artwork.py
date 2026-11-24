"""Opt-in image SEARCH, review and local editing. No image-generation or Steam API.

Search results can be wrong or copyrighted. Nothing is applied automatically.
Only explicitly selected public HTTPS image URLs are downloaded and decoded.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import re
import socket
import urllib.parse
import urllib.request

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_DOWNLOAD = 12 * 1024 * 1024
MAX_PIXELS = 36_000_000
TIMEOUT = 9
AGENT = 'PlayDock/0.6.3 (personal artwork browser; no automated reproduction)'


@dataclass(frozen=True)
class Candidate:
    title: str
    image_url: str
    thumbnail_url: str
    source_url: str
    provider: str
    width: int = 0
    height: int = 0
    license_label: str = ''


# Filename labels are not necessarily part of the game's published title.
# A chapter number, unlike a version or translation tag, distinguishes games:
# "Chap.1" and "Chapter 2" must never be mixed in image results.
_RELEASE_TAG = re.compile(
    r"(?i)^(?:v(?:er(?:sion)?)?[\s._-]*\d[\w. -]*|\d[\d. _-]*|"
    r"수정\s*\d*|한글(?:어)?(?:패치)?[^]]*|한국어[^]]*|번역[^]]*|"
    r"pc|steam[^]]*|(?:rj|vj|bj|ej)\d{5,8}|fix\s*\d+)$"
)
_CHAPTER = re.compile(r"(?i)(?<![a-z])(?:chapter|chap|ch)[.\s:_-]*(\d{1,3})(?!\d)")


def _title_search_variants(query: str) -> list[str]:
    """Equivalent punctuation/spelling of a chapter, retaining its number."""
    variants = [query]
    ch = _CHAPTER.search(query)
    if ch:
        base = query[:ch.start()].rstrip(' -:([_')
        rest = query[ch.end():].lstrip(' )]')
        if base:
            variants.append(f'{base} Chap.{ch.group(1)}' + (f' {rest}' if rest else ''))
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))


def _clean_one_search_title(raw: str) -> str:
    raw = re.sub(r'\.(?:zip|7z|rar)$', '', raw.strip(), flags=re.I)
    # Remove complete release tags only. Never trim an unmatched bracket from
    # an otherwise valid name: the old .strip(' -_[]') corrupted [Chap.1].
    def rewrite_bracket(match: re.Match) -> str:
        text = match.group(1).strip()
        chapter = _CHAPTER.fullmatch(text)
        if chapter:
            return ' Chapter ' + chapter.group(1)
        return '' if _RELEASE_TAG.fullmatch(text) else '[' + text + ']'

    cleaned = re.sub(r'\[([^\[\]\r\n]{1,90})\]', rewrite_bracket, raw)
    # Also tolerate a partially broken chapter annotation in existing display
    # metadata, without ever treating arbitrary unmatched brackets as a tag.
    cleaned = re.sub(r'(?i)\[\s*(?:chapter|chap|ch)[.\s:_-]*(\d{1,3})\s*$',
                     lambda m: ' Chapter ' + m.group(1), cleaned)
    # Remove standalone version suffixes (e.g. PASEC_v2.2566 or ver0.402).
    cleaned = re.sub(r'(?i)(?:[_\s-]+)(?:ver(?:sion)?[._ -]*|v)\d+(?:[.\-_]\d+)*\s*$', '', cleaned)
    cleaned = re.sub(r'(?i)(?:[_\s-]+)(?:kor|kr)(?:[_\s-]*fix\d+)?\s*$', '', cleaned)
    cleaned = re.sub(r'(?i)[_.-]+(?=v\d)', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' \t\r\n-_')
    # Use uniform Chapter spelling for searches, but keep the number: an
    # image for Chapter 2 is not suitable for Chapter 1.
    cleaned = _CHAPTER.sub(lambda m: 'Chapter ' + m.group(1), cleaned)
    return cleaned[:120]


def suggest_query(*titles: str) -> str:
    """Extract the searchable game title without damaging chapter labels.

    Original titles/filenames and saved metadata are never changed here.
    """
    for raw in titles:
        if not raw:
            continue
        code_match = re.search(r'\b(?:RJ|VJ|BJ|EJ)\d{5,8}\b', raw, re.I)
        cleaned = _clean_one_search_title(str(raw))
        if len(cleaned) >= 3 and not re.fullmatch(r'(?:RJ|VJ|BJ|EJ)\d+', cleaned, re.I):
            return cleaned
        if code_match:
            return code_match.group(0).upper()
    return (titles[0] if titles else '').strip()[:120]


def _https_public_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2400:
        raise ValueError('이미지 주소가 올바르지 않습니다.')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)):
        raise ValueError('외부 공개 HTTPS 이미지 주소만 사용할 수 있습니다.')
    host = parsed.hostname.rstrip('.').lower()
    if host in {'localhost', 'localhost.localdomain'} or host.endswith(('.local', '.localhost', '.internal')):
        raise ValueError('내부 네트워크 주소는 사용할 수 없습니다.')
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError('비공개 네트워크 주소는 사용할 수 없습니다.')
    except ValueError as exc:
        # A ValueError thrown by is_global must not fall through as a hostname.
        if '비공개' in str(exc):
            raise
        if re.fullmatch(r'[0-9.]+', host):
            raise ValueError('숫자로 된 잘못된 주소입니다.') from exc
    return url


def _check_dns(url: str):
    host = urllib.parse.urlsplit(_https_public_url(url)).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('이미지 서버 주소를 확인할 수 없습니다.') from exc
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError('사설망·로컬 서버에서 이미지를 가져올 수 없습니다.')


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_dns(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url: str, limit: int = MAX_DOWNLOAD) -> bytes:
    _check_dns(url)
    opener = urllib.request.build_opener(_SafeRedirect())
    req = urllib.request.Request(url, headers={'User-Agent': AGENT,
                                                'Accept': 'image/png,image/jpeg,image/webp,image/gif,application/json,*/*;q=0.5'})
    with opener.open(req, timeout=TIMEOUT) as response:
        typ = response.headers.get('Content-Type', '').lower()
        if 'html' in typ or 'xml' in typ:
            raise ValueError('이미지 대신 웹페이지가 반환되었습니다.')
        size = response.headers.get('Content-Length')
        if size and size.isdigit() and int(size) > limit:
            raise ValueError('이미지 크기가 12MB 제한을 초과했습니다.')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('파일이 허용 크기를 초과했습니다.')
    return data


def read_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_DOWNLOAD:
        raise ValueError('이미지 데이터의 크기가 유효하지 않습니다.')
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
                raise ValueError('PNG/JPEG/WebP/GIF 이미지만 지원합니다.')
            if im.width < 64 or im.height < 64 or im.width * im.height > MAX_PIXELS:
                raise ValueError('이미지 해상도가 너무 작거나 큽니다.')
            im.seek(0)
            image = ImageOps.exif_transpose(im)
            return image.convert('RGBA')
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError('다운로드 파일이 정상 이미지가 아닙니다.') from exc


def download_image(url: str) -> bytes:
    raw = _get(url)
    read_image(raw)  # validate before reaching GUI/editor/cache
    return raw


def _crop_geometry(image_size: tuple[int, int], kind: str, zoom: int):
    """Source crop size and available motion for pan controls.

    At 100% this matches an aspect-fit crop; zooming in produces room to
    reposition the image even when its original aspect matches the target.
    """
    if kind not in {'hero', 'icon'}:
        raise ValueError('배너 또는 아이콘만 지원합니다.')
    if not 100 <= zoom <= 180:
        raise ValueError('확대 비율은 100~180%만 사용할 수 있습니다.')
    width, height = image_size
    ratio = 1600 / 520 if kind == 'hero' else 1.0
    if width / height > ratio:
        base_width, base_height = height * ratio, height
    else:
        base_width, base_height = width, width / ratio
    crop_width = base_width * 100 / zoom
    crop_height = base_height * 100 / zoom
    return crop_width, crop_height, max(0., width - crop_width), max(0., height - crop_height)


def crop_pan_center(image_size: tuple[int, int], kind: str,
                    center_x: float, center_y: float, zoom: int,
                    drag_x: float, drag_y: float,
                    preview_size: tuple[int, int]) -> tuple[float, float]:
    """Drag image pixels; moving image right shows an earlier/left source area."""
    crop_w, crop_h, travel_x, travel_y = _crop_geometry(image_size, kind, zoom)
    preview_w, preview_h = preview_size
    def shift(center, delta, crop_pixels, travel, preview_pixels):
        if preview_pixels <= 0 or travel <= 1e-7:
            return center
        step = delta * crop_pixels / preview_pixels / travel * 100
        return min(100., max(0., center - step))
    return (shift(center_x, drag_x, crop_w, travel_x, preview_w),
            shift(center_y, drag_y, crop_h, travel_y, preview_h))


def crop_art(image: Image.Image, kind: str, center_x: int = 50, center_y: int = 50,
             zoom: int = 100, *, preview: bool = False) -> Image.Image:
    """Crop exact area selected by the sliders/drag (not generative editing)."""
    if not (0 <= center_x <= 100 and 0 <= center_y <= 100):
        raise ValueError('이미지 편집 범위를 벗어났습니다.')
    crop_w, crop_h, travel_x, travel_y = _crop_geometry(image.size, kind, zoom)
    left, top = travel_x * center_x / 100, travel_y * center_y / 100
    output = (640, 208) if preview and kind == 'hero' else ((1600, 520) if kind == 'hero' else (256, 256))
    img = image.convert('RGB' if kind == 'hero' else 'RGBA')
    return img.resize(output, Image.Resampling.LANCZOS,
                      box=(left, top, left + crop_w, top + crop_h))


def crop_png(data: bytes, kind: str, center_x: int = 50, center_y: int = 50,
             zoom: int = 100, *, preview: bool = False) -> bytes:
    result = crop_art(read_image(data), kind, center_x, center_y, zoom, preview=preview)
    buffer = BytesIO()
    result.save(buffer, format='PNG', optimize=not preview)
    return buffer.getvalue()


def save_selected_art(data: bytes, target: Path, kind: str, center_x: int = 50,
                      center_y: int = 50, zoom: int = 100) -> None:
    """Atomic write; caller must ask before overwriting existing art."""
    content = crop_png(data, kind, center_x, center_y, zoom)
    target = Path(target)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('링크된 캐시 위치에 저장할 수 없습니다.')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.writing')
    try:
        with temp.open('wb') as stream:
            stream.write(content)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def _normalize_ddgs(rows: list[dict]) -> list[Candidate]:
    result = []
    for row in rows:
        image = row.get('image', '')
        thumb = row.get('thumbnail', '')
        try:
            _https_public_url(image)
        except (ValueError, TypeError):
            continue
        if thumb:
            try:
                _https_public_url(thumb)
            except (ValueError, TypeError):
                thumb = ''
        source = row.get('url', '')
        try:
            _https_public_url(source)
        except (ValueError, TypeError):
            source = ''
        result.append(Candidate(str(row.get('title', '이미지 후보'))[:140], image, thumb or image,
                                source, '웹 이미지 검색',
                                int(row.get('width') or 0), int(row.get('height') or 0),
                                '사용 권한 미확인'))
    return result


def _commons_search(query: str, max_results: int = 8) -> list[Candidate]:
    params = {
        'action': 'query', 'format': 'json', 'formatversion': '2',
        'generator': 'search', 'gsrsearch': query, 'gsrnamespace': '6',
        'gsrlimit': str(max_results), 'prop': 'imageinfo',
        'iiprop': 'url|mime|size|extmetadata', 'iiurlwidth': '400',
        'iiextmetadatafilter': 'LicenseShortName|Artist',
    }
    endpoint = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params)
    payload = json.loads(_get(endpoint, 2 * 1024 * 1024))
    result = []
    for page in payload.get('query', {}).get('pages', []):
        info = (page.get('imageinfo') or [{}])[0]
        if info.get('mime') not in ('image/png', 'image/jpeg', 'image/webp'):
            continue
        url = info.get('url', '')
        thumb = info.get('thumburl', '')
        try:
            _https_public_url(url)
            _https_public_url(thumb or url)
        except ValueError:
            continue
        license_label = re.sub(r'<[^>]+>', '', info.get('extmetadata', {}).get('LicenseShortName', {}).get('value', ''))[:80]
        result.append(Candidate(page.get('title', '')[5:][:140], url, thumb or url,
                                info.get('descriptionurl', ''), 'Wikimedia Commons',
                                int(info.get('width', 0)), int(info.get('height', 0)), license_label))
    return result


def _identity_terms(query: str) -> list[str]:
    # Do not let generic terms ("game banner", "Steam artwork") qualify an
    # unrelated image as a match. Ignore a bare version or a single digit.
    words = re.findall(r"[\w가-힣ぁ-ゟァ-ヿ一-龥]+", query.casefold())
    stop = {'game', 'games', 'the', 'and', 'official', 'banner', 'icon', 'art',
            'cover', 'image', 'steam', 'pc', 'dlc', 'patch', 'edition', 'version',
            'rj', 'kr', 'korean'}
    return [word for word in words if len(word) >= 3 and word not in stop and not word.isdigit()]


def _compact_phrase(text: str) -> str:
    # Normalize Chap.1 / ch 1 / Chapter 1 into identical strict tokens.
    # This lets one game's filename and publisher's official spelling agree
    # without accepting related but different chapters.
    decoded = urllib.parse.unquote(text).casefold()
    decoded = _CHAPTER.sub(lambda m: 'chapter' + m.group(1), decoded)
    return ''.join(re.findall(r'[\w가-힣ぁ-ゟァ-ヿ一-龥]+', decoded))


def candidate_matches_game(candidate: Candidate, game_title: str,
                           product_code: str | None = None) -> bool:
    """Conservative match: exact work code OR exact multiword title phrase.

    Loose token overlap matched unrelated Korean titles such as one containing
    '6월' or '너와'. Such hits must never become automatic artwork suggestions.
    """
    hay = candidate.title + ' ' + candidate.source_url
    # 'Chapter 1' must never match 'Chapter 10'. Substring comparison alone
    # would allow that because compact text 'chapter1' prefixes 'chapter10'.
    expected_chapter = _CHAPTER.search(game_title)
    if expected_chapter:
        encountered = set(_CHAPTER.findall(urllib.parse.unquote(hay)))
        if encountered and encountered != {expected_chapter.group(1)}:
            return False
    if product_code:
        expected = product_code.upper()
        codes = {m.upper() for m in re.findall(r'(?<![A-Z0-9])(?:RJ|VJ|BJ|EJ)\d{6,8}(?!\d)',
                                               urllib.parse.unquote(hay), re.I)}
        if codes:
            return codes == {expected}
    normalized = _compact_phrase(game_title)
    if len(normalized) < 4:
        return False
    # If title includes a numbered sequel, an image for another sequel is not
    # a safe replacement (BUZAMA 1 is not BUZAMA 2).
    number = re.search(r'(?<!\d)(\d{1,3})\s*$', game_title)
    if number:
        base = _compact_phrase(game_title[:number.start()])
        if base and re.search(re.escape(base) + r'(\d{1,3})', _compact_phrase(hay)):
            listed = re.findall(re.escape(base) + r'(\d{1,3})', _compact_phrase(hay))
            if listed and any(n != number.group(1) for n in listed):
                return False
    return normalized in _compact_phrase(hay)


def search_images(query: str, kind: str = 'hero', limit: int = 9,
                  *, product_code: str | None = None) -> list[Candidate]:
    """Search by verified code first, otherwise exact title, never loose art.

    The product code, when supplied, is attached to search queries. Results
    with a *different* work code cannot match the requested game.
    """
    query = query.strip()[:130]
    if len(query) < 2:
        raise ValueError('검색할 게임 이름을 두 글자 이상 입력하세요.')
    if kind not in {'hero', 'icon'}:
        raise ValueError('이미지 종류가 잘못되었습니다.')
    if product_code and not re.fullmatch(r'(?:RJ|VJ|BJ|EJ)\d{6,8}', product_code, re.I):
        raise ValueError('작품 코드가 올바르지 않습니다.')
    product_code = product_code.upper() if product_code else None
    errors = []
    try:
        from ddgs import DDGS
        with DDGS(timeout=12) as ddgs:
            kind_words = (' cover artwork' if kind == 'hero' else ' icon cover')
            requests = ([f'"{product_code}" "{query}"' + kind_words,
                         f'"{product_code}" DLsite image'] if product_code else [])
            kind_words = ' game banner key art' if kind == 'hero' else ' game icon cover'
            # Chapter spellings differ between local ZIP names and publisher
            # pages. Search both, but require strict chapter-aware matching.
            requests += ['"' + variant + '"' + kind_words
                         for variant in _title_search_variants(query)[:2]]
            matches = []
            for exact_query in requests:
                rows = ddgs.images(exact_query, max_results=max(limit + 8, 16),
                                   safesearch='moderate',
                                   layout='Wide' if kind == 'hero' else 'Square')
                candidates = _normalize_ddgs(rows or [])
                matches.extend(c for c in candidates if candidate_matches_game(c, query, product_code))
            if matches:
                return _rank_unique(matches, kind, game_title=query, product_code=product_code)[:limit]
    except Exception as exc:
        errors.append(f'웹 이미지 검색: {type(exc).__name__}')
    try:
        candidates = _commons_search(f'{query} {product_code or ""}', max_results=limit)
        matches = [c for c in candidates if candidate_matches_game(c, query, product_code)]
        if matches:
            return _rank_unique(matches, kind, game_title=query, product_code=product_code)[:limit]
    except Exception as exc:
        errors.append(f'Wikimedia: {type(exc).__name__}')
    raise RuntimeError('정확한 작품명 또는 작품 코드와 연결된 이미지가 없습니다. '
                       '다른 작품 이미지를 임의로 표시하지 않습니다. 브라우저에서 직접 확인하세요. '
                       + ', '.join(errors))


def _rank_unique(candidates: list[Candidate], kind: str,
                 game_title: str = '', product_code: str | None = None) -> list[Candidate]:
    seen = set()
    distinct = []
    for c in candidates:
        if c.image_url in seen:
            continue
        seen.add(c.image_url)
        distinct.append(c)
    ratio = 1600 / 520 if kind == 'hero' else 1.0
    def priority(c):
        if c.width > 0 and c.height > 0:
            quality = min(c.width * c.height / 500000, 1.0)
            aspect = abs(__import__('math').log(max(c.width / c.height, 0.01) / ratio))
        else:
            quality, aspect = 0, 2.0
        keywords = ('banner', 'header', 'key art', 'wallpaper') if kind == 'hero' else ('icon', 'cover', 'logo')
        matched = sum(term in c.title.casefold() for term in keywords)
        score = aspect - matched * 0.4 - quality * 0.3
        if product_code and product_code.lower() in (c.title + ' ' + c.source_url).lower():
            score -= 3.0  # code-confirmed artwork wins over similar-looking titles
        if game_title:
            hay = (c.title + ' ' + c.source_url).casefold()
            # Prefer genuine work pages over thumbnails of commentary videos,
            # Pinterest boards, stock graphics, and generic design templates.
            if any(site in c.source_url.casefold() for site in ('dlsite.com', 'itch.io', 'store.steampowered.com')):
                score -= 0.7
            if 'official' in hay or 'key visual' in hay or 'key art' in hay:
                score -= 0.2
            if any(word in hay for word in ('youtube.com', 'youtu.be', 'pinterest.',
                                            'template', 'stock photo', 'freepik', 'deviantart')):
                score += 1.2
        return score
    return sorted(distinct, key=priority)
