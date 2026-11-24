"""Optional DLsite single-work HTTP lookup via the website's undocumented JSON.

Networking never runs while constructing the local SQLite database.
"""
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json
import re
from models.game_codes import normalize_code
from product_titles import clean_title

CATEGORIES = ('maniax', 'home', 'soft', 'girls', 'pro')
LOCALES = {'ja': 'ja_JP', 'ko': 'ko_KR', 'en': 'en_US'}
MAX_RESPONSE = 2_000_000
MAX_TAGS = 100
MAX_IMAGES = 40


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def _safe_text(value, length=300) -> str:
    return re.sub(r'\s+', ' ', value).strip()[:length] if isinstance(value, str) else ''

def _safe_dlsite_url(value) -> str:
    """Only store links from DLsite domains over HTTPS, no user-controlled URLs."""
    if not isinstance(value, str):
        return ''
    raw = value.strip()
    if raw.startswith('//'):
        raw = 'https:' + raw
    try:
        parts = urlsplit(raw)
        domain = (parts.hostname or '').lower()
        if parts.scheme != 'https' or parts.username or parts.password:
            return ''
        if domain not in ('dlsite.com', 'dlsite.jp') and not domain.endswith(('.dlsite.com', '.dlsite.jp')):
            return ''
        return raw[:2048]
    except ValueError:
        return ''

def _image_urls(value):
    """DLsite has used objects with `url`, `src`, and lists of similar objects."""
    if isinstance(value, str):
        url = _safe_dlsite_url(value)
        return [url] if url else []
    if isinstance(value, dict):
        for key in ('url', 'src', 'image_url'):
            if key in value:
                return _image_urls(value[key])
        return []
    if isinstance(value, list):
        urls = []
        for item in value[:MAX_IMAGES]:
            urls.extend(_image_urls(item))
        return urls[:MAX_IMAGES]
    return []

def _extract_payload(raw, code: str) -> dict | None:
    """Accept only matching workno; never cross-match a different work."""
    code = normalize_code(code)
    if isinstance(raw, list):
        for candidate in raw[:50]:
            result = _extract_payload(candidate, code)
            if result:
                return result
        return None
    if not isinstance(raw, dict):
        return None
    if code in raw:
        return _extract_payload(raw[code], code)
    for key in ('products', 'items', 'data'):
        if key in raw and isinstance(raw[key], (list, dict)):
            match = _extract_payload(raw[key], code)
            if match:
                return match
    id_in_payload = raw.get('workno') or raw.get('work_no') or raw.get('product_id') or raw.get('work_id')
    if str(id_in_payload or '').upper() != code:
        return None
    return raw

def _parse_tags(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    labels = []
    for entry in raw[:MAX_TAGS]:
        value = entry.get('name') or entry.get('genre_name') if isinstance(entry, dict) else entry
        label = _safe_text(value, 80)
        if label and label not in labels:
            labels.append(label)
    return labels

def fetch_dlsite_work(code: str, *, opener=urlopen, categories=CATEGORIES,
                      locales=LOCALES, timeout=8.0) -> dict:
    """Fetch a *single* user-selected product via DLsite's non-public JSON.

    Never batch-crawl, follow product links, or request personal endpoints.
    The caller must run this in a background worker, not the UI thread.
    """
    code = normalize_code(code)
    if not code:
        raise ValueError('작품 코드가 필요합니다.')
    found = None
    chosen_category = None
    titles: dict[str, str] = {}
    source = ''
    failures = []
    for category in categories:
        for language, locale in locales.items():
            url = 'https://www.dlsite.com/' + category + '/api/=/product.json?' + urlencode({'workno': code, 'locale': locale})
            request = Request(url, headers={'User-Agent': 'PlayDock/0.8.0 (personal metadata lookup)',
                                            'Accept': 'application/json'})
            try:
                with opener(request, timeout=timeout) as response:
                    if hasattr(response, 'status') and response.status != 200:
                        continue
                    blob = response.read(MAX_RESPONSE + 1)
                if len(blob) > MAX_RESPONSE:
                    raise ValueError('DLsite 응답이 제한 크기를 초과했습니다.')
                item = _extract_payload(json.loads(blob.decode('utf-8-sig')), code)
                if not item:
                    continue
                if found is None:
                    found = item
                    chosen_category = category
                    source = url
                work_name = clean_title(item.get('work_name') or item.get('title'))
                if work_name:
                    # Requested locale is NOT proof that the text was translated.
                    if language == 'ko' and re.search(r'[\uac00-\ud7a3]', work_name):
                        titles[language] = work_name
                    elif language == 'ja' and not re.search(r'[\uac00-\ud7a3]', work_name):
                        titles[language] = work_name
                    elif language == 'en' and not re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]', work_name):
                        titles[language] = work_name
            except (OSError, ValueError, UnicodeError, TypeError, TimeoutError) as exc:
                failures.append(str(exc)[:120])
                continue
        if found is not None:
            break
    if found is None:
        raise LookupError('DLsite에서 해당 작품 코드를 확인하지 못했습니다. 사이트 차단·품번 변경·비공개 작품일 수 있습니다.')
    default_title = clean_title(found.get('work_name') or found.get('title')) or code
    if not titles:
        titles['ja'] = default_title
    images = []
    for kind, key in (('cover', 'image_main'), ('thumbnail', 'image_thum'), ('sample', 'image_samples')):
        for position, url in enumerate(_image_urls(found.get(key))):
            if len(images) >= MAX_IMAGES:
                break
            images.append({'kind': kind, 'position': position, 'url': url})
    category = chosen_category or 'maniax'
    page = f'https://www.dlsite.com/{category}/work/=/product_id/{code}.html'
    return {
        'code': code, 'titles': titles, 'fallback_title': default_title,
        'maker': _safe_text(found.get('maker_name'), 180),
        'release_date': _safe_text(found.get('regist_date') or found.get('release_date'), 35),
        'tags': _parse_tags(found.get('genres') or found.get('genres_replaced') or []),
        'images': images,
        'page_url': page,
        'source_url': source,
        'source_type': 'DLsite website JSON (undocumented endpoint)',
        'retrieved_at': _timestamp(),
    }
