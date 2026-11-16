"""Per-user SQLite work repository (does not perform network requests)."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from game_codes import normalize_code
from product_titles import clean_title
from integrations.dlsite_client import (
    LOCALES, MAX_TAGS, MAX_IMAGES, _timestamp, _safe_text, _safe_dlsite_url,
)

SCHEMA_VERSION = 1


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
