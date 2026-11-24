"""Local-only SQLite work catalogue for PlayDock.

DLsite JSON is a site-internal, *undocumented* endpoint.  The database never
ships with users' records and remote lookup only happens on explicit request.
No executable, archive, account cookie, API key or image bytes are uploaded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json
import re
import sqlite3

from game_codes import normalize_code
from product_titles import clean_title

SCHEMA_VERSION = 1
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


class WorkDatabase:
    """Short-lived SQLite connections; safe to back up when GUI is idle."""

    def __init__(self, store: Path):
        self.path = Path(store) / 'playdock.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        """Commit/rollback the transaction and always release the SQLite file handle.

        sqlite3.Connection.__exit__ handles transactions but does NOT close the
        connection; keeping it open prevents file replacement on Windows.
        """
        conn = sqlite3.connect(self.path, timeout=5.0)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=5000')
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with self.connect() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('새로운 PlayDock DB 형식입니다. 프로그램을 업데이트하세요.')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS works (
                    code TEXT PRIMARY KEY,
                    fallback_title TEXT NOT NULL,
                    maker TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL DEFAULT '',
                    page_url TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT '',
                    retrieved_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS work_titles (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    lang TEXT NOT NULL CHECK(lang IN ('ko', 'ja', 'en')),
                    title TEXT NOT NULL,
                    PRIMARY KEY(code, lang)
                );
                CREATE TABLE IF NOT EXISTS work_tags (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    tag TEXT NOT NULL,
                    PRIMARY KEY(code, tag)
                );
                CREATE TABLE IF NOT EXISTS work_images (
                    code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    PRIMARY KEY(code, kind, position)
                );
                CREATE TABLE IF NOT EXISTS library_links (
                    game_id TEXT PRIMARY KEY,
                    raw_name TEXT NOT NULL,
                    archive_name TEXT,
                    product_code TEXT,
                    last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_library_links_code ON library_links(product_code);
                PRAGMA user_version=1;
            ''')

    def sync_library(self, library, games):
        """Record scanned archives and code links; never delete missing games.

        No network calls, metadata edits, or installed game modifications.
        """
        now = _timestamp()
        with self.connect() as con:
            con.executemany('''INSERT INTO library_links(game_id, raw_name, archive_name, product_code, last_seen)
                VALUES(?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET
                raw_name=excluded.raw_name, archive_name=excluded.archive_name,
                product_code=excluded.product_code, last_seen=excluded.last_seen''',
                ((g.id, g.name, g.archive.name if g.archive else None,
                  library.product_code(g) or None, now) for g in games))

    def save_work(self, record: dict):
        code = normalize_code(record.get('code'))
        if not code:
            raise ValueError('작품 코드가 필요합니다.')
        titles = record.get('titles', {})
        if not isinstance(titles, dict):
            raise ValueError('언어별 제목이 잘못됐습니다.')
        title = clean_title(record.get('fallback_title'))
        if not title:
            raise ValueError('작품명이 올바르지 않습니다.')
        with self.connect() as con:
            con.execute('''INSERT INTO works(code, fallback_title, maker, release_date, page_url, source_url,
                            source_type, retrieved_at) VALUES(?,?,?,?,?,?,?,?)
                            ON CONFLICT(code) DO UPDATE SET fallback_title=excluded.fallback_title,
                            maker=excluded.maker, release_date=excluded.release_date,
                            page_url=excluded.page_url, source_url=excluded.source_url,
                            source_type=excluded.source_type, retrieved_at=excluded.retrieved_at''',
                        (code, title, _safe_text(record.get('maker'), 180),
                         _safe_text(record.get('release_date'), 35),
                         _safe_dlsite_url(record.get('page_url')),
                         _safe_dlsite_url(record.get('source_url')),
                         _safe_text(record.get('source_type'), 150),
                         record.get('retrieved_at') or _timestamp()))
            con.execute('DELETE FROM work_titles WHERE code=?', (code,))
            for lang, value in titles.items():
                if lang in LOCALES and clean_title(value):
                    con.execute('INSERT INTO work_titles VALUES (?,?,?)', (code, lang, clean_title(value)))
            con.execute('DELETE FROM work_tags WHERE code=?', (code,))
            for tag in list(dict.fromkeys(_safe_text(v, 80) for v in record.get('tags', [])))[:MAX_TAGS]:
                if tag:
                    con.execute('INSERT INTO work_tags VALUES (?,?)', (code, tag))
            con.execute('DELETE FROM work_images WHERE code=?', (code,))
            for image in record.get('images', [])[:MAX_IMAGES]:
                if not isinstance(image, dict):
                    continue
                url = _safe_dlsite_url(image.get('url'))
                kind = image.get('kind')
                if url and kind in ('cover', 'thumbnail', 'sample'):
                    try:
                        position = int(image.get('position', 0))
                        con.execute('INSERT OR REPLACE INTO work_images VALUES(?,?,?,?)', (code, kind, position, url))
                    except (TypeError, ValueError):
                        continue

    def get_work(self, code: str) -> dict | None:
        code = normalize_code(code)
        if not code:
            return None
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute('SELECT * FROM works WHERE code=?', (code,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result['titles'] = {r['lang']: r['title'] for r in con.execute(
                'SELECT lang, title FROM work_titles WHERE code=?', (code,))}
            result['tags'] = [r['tag'] for r in con.execute(
                'SELECT tag FROM work_tags WHERE code=? ORDER BY tag', (code,))]
            result['images'] = [dict(r) for r in con.execute(
                'SELECT kind, position, url FROM work_images WHERE code=? ORDER BY kind, position', (code,))]
            return result

    def count_works(self) -> int:
        with self.connect() as con:
            return con.execute('SELECT COUNT(*) FROM works').fetchone()[0]
