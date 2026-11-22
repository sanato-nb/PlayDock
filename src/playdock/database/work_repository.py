"""Per-user SQLite work repository (does not perform network requests)."""
from __future__ import annotations
from contextlib import contextmanager, closing
from pathlib import Path
import sqlite3

from database.official_catalog import default_catalog_path, _valid_identity
from game_codes import normalize_code
from product_titles import clean_title
from integrations.dlsite_client import (
    LOCALES, MAX_TAGS, MAX_IMAGES, _timestamp, _safe_text, _safe_dlsite_url,
)

SCHEMA_VERSION = 2


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
                CREATE TABLE IF NOT EXISTS official_works (
                    store TEXT NOT NULL CHECK(store IN ('dlsite', 'steam')),
                    product_id TEXT NOT NULL,
                    official_title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    page_url TEXT NOT NULL,
                    verified_at_utc TEXT NOT NULL,
                    PRIMARY KEY(store, product_id)
                );
                PRAGMA user_version=2;
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

    def import_scanner_catalog(self, source: Path | None = None) -> int:
        """Copy verified DLsite/Steam facts into PlayDock's own backed-up DB.

        Read the independent scanner database without modifying or moving it.
        Do not modify any existing works, library_links, user titles or games.
        Re-import is idempotent and newer timestamps take precedence.
        """
        path = Path(source) if source is not None else default_catalog_path()
        if not path.is_file() or path.is_symlink():
            return 0
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as upstream:
                upstream.execute("PRAGMA query_only=ON")
                records = upstream.execute("""
                    SELECT store, product_id, official_title, category,
                           page_url, verified_at_utc
                    FROM official_works LIMIT 10001
                """).fetchall()
        except sqlite3.DatabaseError as exc:
            raise ValueError("정체 판독기 작품 DB를 읽지 못했습니다.") from exc
        if len(records) > 10000:
            raise ValueError("정체 판독기 작품 DB가 안전한 가져오기 한도를 초과했습니다.")
        valid = []
        for record in records:
            if not all(isinstance(value, str) for value in record):
                continue
            store, pid, title, category, url, verified = record
            if (not title.strip() or len(title) > 1000 or len(category) > 240 or
                    len(url) > 2048 or len(verified) > 48 or
                    not _valid_identity(store, pid, url)):
                continue
            valid.append((store, pid, title, category, url, verified))
        if not valid:
            return 0
        with self.connect() as con:
            con.executemany("""
                INSERT INTO official_works
                    (store, product_id, official_title, category, page_url, verified_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(store, product_id) DO UPDATE SET
                    official_title=excluded.official_title,
                    category=excluded.category,
                    page_url=excluded.page_url,
                    verified_at_utc=excluded.verified_at_utc
                WHERE official_works.verified_at_utc <= excluded.verified_at_utc
            """, valid)
        return len(valid)

    def get_official_work(self, store: str, product_id: str) -> dict | None:
        """Read imported public store metadata without network calls."""
        store = str(store).strip().lower()
        pid = str(product_id).strip().upper() if store == "dlsite" else str(product_id).strip()
        if not _valid_identity(store, pid,
                               f"https://www.dlsite.com/a/{pid}" if store == "dlsite"
                               else f"https://store.steampowered.com/app/{pid}/"):
            return None
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute("""
                SELECT store, product_id, official_title, category,
                       page_url, verified_at_utc
                FROM official_works
                WHERE store=? AND product_id=?
            """, (store, pid)).fetchone()
            return dict(row) if row else None

    def count_official_works(self) -> int:
        with self.connect() as con:
            return con.execute('SELECT COUNT(*) FROM official_works').fetchone()[0]
