"""One PlayDock SQLite database: works and local-game links (schema v3).

All sites use (store, code). Language titles, tags and remote image URLs
belong to the work itself and are stored as JSON, not duplicated child tables.
Old v1/v2 databases are backed up then migrated in a single transaction.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid

from database.official_catalog import _valid_identity, legacy_catalog_path
from game_codes import normalize_code
from product_titles import clean_title
from integrations.dlsite_client import (
    LOCALES, MAX_TAGS, MAX_IMAGES, _timestamp, _safe_text, _safe_dlsite_url,
)

SCHEMA_VERSION = 3
_IMPORT_MARKER = 0x50444B33
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS works (
        store TEXT NOT NULL,
        code TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '',
        maker TEXT NOT NULL DEFAULT '',
        page_url TEXT NOT NULL DEFAULT '',
        checked_at TEXT NOT NULL DEFAULT '',
        titles_json TEXT NOT NULL DEFAULT '{}',
        tags_json TEXT NOT NULL DEFAULT '[]',
        images_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY(store, code)
    )""",
    """CREATE TABLE IF NOT EXISTS library_links (
        game_id TEXT PRIMARY KEY,
        store TEXT NOT NULL DEFAULT '',
        code TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE INDEX IF NOT EXISTS idx_links_site_code
       ON library_links(store, code)""",
)
_DEPRECATED = ("work_titles", "work_tags", "work_images", "official_works")


def _json(value, default):
    if value is None:
        return default
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return default
    return result if isinstance(result, type(default)) else default


def _record(row):
    value = dict(row)
    value["fallback_title"] = value["title"]
    value["official_title"] = value["title"]
    value["product_id"] = value["code"]
    value["retrieved_at"] = value["checked_at"]
    value["verified_at_utc"] = value["checked_at"]
    value["titles"] = _json(value["titles_json"], {})
    value["tags"] = _json(value["tags_json"], [])
    value["images"] = _json(value["images_json"], [])
    return value


def _tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, name):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}


class WorkDatabase:
    """Shared B-location PlayDock DB; supports legacy DLsite call signatures."""

    def __init__(self, store: Path, *, db_path: Path | None = None,
                 import_legacy: bool = False):
        self.path = Path(db_path) if db_path is not None else Path(store) / "playdock.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_import_error = ""
        self.initialize()
        if import_legacy:
            try:
                self._import_old_scanner_once()
            except (OSError, ValueError, sqlite3.Error) as exc:
                # Never prevent PlayDock startup for an inaccessible legacy DB.
                self.legacy_import_error = str(exc)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=8.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=8000")
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with closing(sqlite3.connect(self.path, timeout=8.0)) as conn:
            conn.row_factory = sqlite3.Row
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("최신 PlayDock DB 형식입니다. 프로그램을 업데이트하세요.")
            names = _tables(conn)
            if not (names & (set(_DEPRECATED) | {"works", "library_links"})):
                with conn:
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                return
            if (version == SCHEMA_VERSION and set(_SCHEMA_TABLES).issubset(names)
                    and not (set(_DEPRECATED) & names)
                    and "release_date" not in _columns(conn, "works")
                    and "last_seen" not in _columns(conn, "library_links")):
                return
            checked = conn.execute("PRAGMA quick_check").fetchone()
            if not checked or checked[0] != "ok":
                raise ValueError("기존 PlayDock DB에 무결성 오류가 있어 이전하지 않았습니다.")
            self._snapshot(conn)
            # DDL and all row-copy operations are one SQLite transaction.
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._migrate(conn, names)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.execute("PRAGMA foreign_keys=ON")

    def _snapshot(self, conn):
        backup_root = self.path.parent / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        destination = backup_root / f"playdock_pre_v3_{name}_{uuid.uuid4().hex[:6]}.db"
        with closing(sqlite3.connect(destination)) as backup:
            conn.backup(backup)
            if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("이전 전 SQLite 백업 검증에 실패했습니다.")

    def _migrate(self, conn, names):
        # Rebuild with minimal two-table schema, preserving detailed old records.
        conn.execute("DROP TABLE IF EXISTS __pd_works_v3")
        conn.execute("DROP TABLE IF EXISTS __pd_links_v3")
        works = {}
        if "works" in names:
            for row in conn.execute("SELECT * FROM works"):
                d = dict(row)
                code = str(d.get("code") or "").strip()
                if not code:
                    continue
                store = str(d.get("store") or "dlsite").strip().lower()
                if store == "dlsite":
                    code = code.upper()
                title = d.get("title") or d.get("fallback_title") or code
                key = (store, code)
                works[key] = {
                    "store": store, "code": code, "title": str(title),
                    "category": str(d.get("category") or ""),
                    "maker": str(d.get("maker") or ""),
                    "page_url": str(d.get("page_url") or ""),
                    "checked_at": str(d.get("checked_at") or
                                      d.get("retrieved_at") or ""),
                    "titles_json": str(d.get("titles_json") or "{}"),
                    "tags_json": str(d.get("tags_json") or "[]"),
                    "images_json": str(d.get("images_json") or "[]"),
                }
        # Fold legacy child tables into their parent row without losing arrays.
        for table, field, convert in (
            ("work_titles", "titles_json", lambda xs: {x["lang"]: x["title"] for x in xs}),
            ("work_tags", "tags_json", lambda xs: [x["tag"] for x in xs]),
            ("work_images", "images_json",
             lambda xs: [{"kind": x["kind"], "position": x["position"],
                          "url": x["url"]} for x in xs]),
        ):
            if table not in names:
                continue
            grouped = {}
            for row in conn.execute(f"SELECT * FROM {table}"):
                d = dict(row)
                code = str(d.get("code") or "").strip().upper()
                store = str(d.get("store") or "dlsite").lower()
                grouped.setdefault((store, code), []).append(d)
            for key, rows in grouped.items():
                if key in works:
                    original = _json(works[key][field], {} if field == "titles_json" else [])
                    merged = convert(rows)
                    if isinstance(original, dict):
                        merged = {**merged, **original}
                    elif isinstance(original, list):
                        merged = original + [x for x in merged if x not in original]
                    works[key][field] = json.dumps(merged, ensure_ascii=False)
        # Prefer existing detailed works title, fill missing data from scanner.
        if "official_works" in names:
            for row in conn.execute("SELECT * FROM official_works"):
                d = dict(row)
                store = str(d.get("store") or "").lower()
                code = str(d.get("product_id") or "").strip()
                code = code.upper() if store == "dlsite" else code
                title = str(d.get("official_title") or "").strip()
                url = str(d.get("page_url") or "")
                if not title or not _valid_identity(store, code, url):
                    continue
                key = (store, code)
                if key not in works:
                    works[key] = {
                        "store": store, "code": code, "title": title,
                        "category": "", "maker": "",
                        "page_url": "", "checked_at": "",
                        "titles_json": "{}", "tags_json": "[]",
                        "images_json": "[]",
                    }
                work = works[key]
                work["category"] = work["category"] or str(d.get("category") or "")
                work["page_url"] = work["page_url"] or url
                work["checked_at"] = max(work["checked_at"],
                                         str(d.get("verified_at_utc") or ""))
        conn.execute("""CREATE TABLE __pd_works_v3 (
            store TEXT NOT NULL, code TEXT NOT NULL, title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '', maker TEXT NOT NULL DEFAULT '',
            page_url TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL DEFAULT '', titles_json TEXT NOT NULL DEFAULT '{}',
            tags_json TEXT NOT NULL DEFAULT '[]', images_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY(store, code))""")
        conn.executemany("""
            INSERT INTO __pd_works_v3
            (store,code,title,category,maker,page_url,
             checked_at,titles_json,tags_json,images_json)
            VALUES (:store,:code,:title,:category,:maker,:page_url,
                    :checked_at,:titles_json,:tags_json,:images_json)
        """, works.values())
        conn.execute("""CREATE TABLE __pd_links_v3 (
            game_id TEXT PRIMARY KEY, store TEXT NOT NULL DEFAULT '',
            code TEXT NOT NULL DEFAULT '')""")
        if "library_links" in names:
            for row in conn.execute("SELECT * FROM library_links"):
                d = dict(row)
                code = str(d.get("code") or d.get("product_code") or "").strip()
                store = str(d.get("store") or ("dlsite" if code else "")).lower()
                if store == "dlsite":
                    code = code.upper()
                conn.execute(
                    "INSERT OR REPLACE INTO __pd_links_v3 VALUES (?,?,?)",
                    (d.get("game_id"), store, code),
                )
        for table in ("work_titles", "work_tags", "work_images",
                      "official_works", "library_links", "works"):
            if table in names:
                conn.execute(f"DROP TABLE {table}")
        conn.execute("ALTER TABLE __pd_works_v3 RENAME TO works")
        conn.execute("ALTER TABLE __pd_links_v3 RENAME TO library_links")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_links_site_code ON library_links(store, code)")

    def _import_old_scanner_once(self):
        with self.connect() as conn:
            done = conn.execute("PRAGMA application_id").fetchone()[0] == _IMPORT_MARKER
        if done:
            return 0
        source = legacy_catalog_path()
        if not source.is_file():
            return 0
        count = self.import_scanner_catalog(source)
        with self.connect() as conn:
            conn.execute(f"PRAGMA application_id={_IMPORT_MARKER}")
        return count

    def _upsert_verified(self, rows):
        """Store validated official facts; never erase detailed maker/tags/etc."""
        normalized = {}
        for item in rows:
            store = str(item.get("store") or "").lower().strip()
            code = str(item.get("code") or "").strip()
            code = code.upper() if store == "dlsite" else code
            title = str(item.get("title") or "").strip()
            page_url = str(item.get("page_url") or "").strip()
            category = str(item.get("category") or "").strip()
            checked = str(item.get("checked_at") or _timestamp())
            if (not title or len(title) > 1000 or len(category) > 240 or
                    len(page_url) > 2048 or len(checked) > 48 or
                    not _valid_identity(store, code, page_url)):
                continue
            normalized[(store, code)] = (store, code, title, category, page_url, checked)
        if not normalized:
            return 0
        with self.connect() as conn:
            conn.executemany("""
                INSERT INTO works (store,code,title,category,page_url,checked_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(store,code) DO UPDATE SET
                    title=CASE WHEN excluded.checked_at >= works.checked_at
                               THEN excluded.title ELSE works.title END,
                    category=CASE WHEN excluded.checked_at >= works.checked_at AND excluded.category != ''
                                  THEN excluded.category ELSE works.category END,
                    page_url=CASE WHEN excluded.checked_at >= works.checked_at
                                  THEN excluded.page_url ELSE works.page_url END,
                    checked_at=MAX(works.checked_at, excluded.checked_at)
            """, normalized.values())
        return len(normalized)

    def save_verified_results(self, results):
        records = []
        for result in results:
            for work in result.works:
                if work.status == "verified":
                    records.append({"store": work.store, "code": work.code,
                                    "title": work.title, "category": work.category,
                                    "page_url": work.url, "checked_at": _timestamp()})
        return self._upsert_verified(records)

    def import_scanner_catalog(self, source: Path | None = None):
        """One-time legacy import: read-only old official_works.sqlite3 source."""
        source = Path(source) if source is not None else legacy_catalog_path()
        if not source.is_file() or source.is_symlink():
            return 0
        if source.resolve() == self.path.resolve():
            return 0
        try:
            with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro",
                                         uri=True, timeout=4)) as upstream:
                upstream.execute("PRAGMA query_only=ON")
                records = upstream.execute("""
                    SELECT store,product_id,official_title,category,page_url,verified_at_utc
                    FROM official_works LIMIT 10001""").fetchall()
        except sqlite3.DatabaseError as exc:
            raise ValueError("이전 정체 판독기 DB를 읽지 못했습니다.") from exc
        if len(records) > 10000:
            raise ValueError("이전 작품 DB 행이 안전 한도를 초과했습니다.")
        return self._upsert_verified([
            {"store": store, "code": code, "title": title,
             "category": category, "page_url": url, "checked_at": checked}
            for store, code, title, category, url, checked in records
        ])

    def save_work(self, record: dict):
        """DLsite detailed lookup; keep existing category and nonempty arrays."""
        code = normalize_code(record.get("code"))
        title = clean_title(record.get("fallback_title"))
        if not code or not title:
            raise ValueError("작품 코드 또는 작품명이 올바르지 않습니다.")
        titles = record.get("titles", {})
        if not isinstance(titles, dict):
            raise ValueError("언어별 제목이 잘못됐습니다.")
        titles = {lang: clean_title(value) for lang, value in titles.items()
                  if lang in LOCALES and clean_title(value)}
        tags = [s for s in dict.fromkeys(
            _safe_text(x, 80) for x in record.get("tags", [])) if s][:MAX_TAGS]
        images = []
        for entry in record.get("images", [])[:MAX_IMAGES]:
            if not isinstance(entry, dict) or entry.get("kind") not in ("cover","thumbnail","sample"):
                continue
            url = _safe_dlsite_url(entry.get("url"))
            try:
                position = int(entry.get("position") or 0)
            except (TypeError, ValueError):
                continue
            if url:
                images.append({"kind": entry["kind"], "position": position, "url": url})
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO works (store,code,title,maker,page_url,checked_at,
                                   titles_json,tags_json,images_json,category)
                VALUES ('dlsite',?,?,?,?,?,?,?,?,?)
                ON CONFLICT(store,code) DO UPDATE SET
                    title=excluded.title,
                    maker=COALESCE(NULLIF(excluded.maker,''),works.maker),
                    page_url=COALESCE(NULLIF(excluded.page_url,''),works.page_url),
                    checked_at=MAX(works.checked_at,excluded.checked_at),
                    titles_json=CASE WHEN excluded.titles_json!='{}'
                                     THEN excluded.titles_json ELSE works.titles_json END,
                    tags_json=CASE WHEN excluded.tags_json!='[]'
                                   THEN excluded.tags_json ELSE works.tags_json END,
                    images_json=CASE WHEN excluded.images_json!='[]'
                                     THEN excluded.images_json ELSE works.images_json END
            """, (code, title, _safe_text(record.get("maker"), 180),
                  _safe_dlsite_url(record.get("page_url")),
                  record.get("retrieved_at") or _timestamp(),
                  json.dumps(titles, ensure_ascii=False),
                  json.dumps(tags, ensure_ascii=False),
                  json.dumps(images, ensure_ascii=False), ""))

    def get_work(self, code: str, *, store: str = "dlsite"):
        if store == "dlsite":
            code = normalize_code(code)
        else:
            code = str(code or "").strip()
        if not code or store not in ("dlsite", "steam"):
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE store=? AND code=?",
                               (store, code)).fetchone()
            return _record(row) if row else None

    def get_official_work(self, store: str, product_id: str):
        store = str(store).strip().lower()
        code = str(product_id or "").strip()
        code = code.upper() if store == "dlsite" else code
        if store not in ("dlsite","steam"):
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE store=? AND code=?",
                               (store, code)).fetchone()
        if not row or not row["page_url"] or not _valid_identity(store, code, row["page_url"]):
            return None
        return _record(row)

    def save_official_image_urls(self, store: str, code: str,
                                 url_by_kind: dict[str, str]) -> int:
        """Keep verified official URL candidates in works.images_json.

        This never downloads or applies an image. Only the user's checkboxes
        may alter local hero.png/icon.png files.
        """
        from services.official_artwork_service import trusted_image_url
        store = str(store).lower()
        code = str(code).upper() if store == "dlsite" else str(code)
        valid = {kind: url for kind, url in url_by_kind.items()
                 if kind in ("hero", "icon") and
                 trusted_image_url(store, code, url)}
        if not valid:
            return 0
        with self.connect() as con:
            record = con.execute(
                "SELECT images_json FROM works WHERE store=? AND code=?",
                (store, code)).fetchone()
            if record is None:
                return 0
            saved = _json(record["images_json"], [])
            remaining = [item for item in saved
                         if isinstance(item, dict) and item.get("kind") not in valid]
            for kind in ("hero", "icon"):
                if kind in valid:
                    remaining.append({"kind": kind, "position": 0, "url": valid[kind]})
            con.execute(
                "UPDATE works SET images_json=? WHERE store=? AND code=?",
                (json.dumps(remaining, ensure_ascii=False), store, code),
            )
        return len(valid)

    def count_works(self):
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]

    def count_official_works(self):
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM works WHERE page_url!=''").fetchone()[0]

    def sync_library(self, library, games):
        """Keep only user-selected code links; automatic IDs remain derived.

        Existing v1/v2 records are retained until the game is scanned, then
        only explicit manual choices are stored.
        """
        from services.official_work_service import explicit_work_identity
        with self.connect() as con:
            for game in games:
                meta = library.meta(game)
                manual = any(k in meta for k in
                             ("product_code", "product_store", "steam_app_id",
                              "artwork_identity_store"))
                identity = explicit_work_identity(library, game) if manual else None
                if not identity:
                    con.execute("DELETE FROM library_links WHERE game_id=?", (game.id,))
                    continue
                store, code = identity
                con.execute("""INSERT INTO library_links(game_id,store,code)
                    VALUES(?,?,?)
                    ON CONFLICT(game_id) DO UPDATE SET
                        store=excluded.store, code=excluded.code""",
                    (game.id, store, code))

    def get_link(self, game_id: str) -> tuple[str, str] | None:
        with self.connect() as con:
            row = con.execute("SELECT store,code FROM library_links WHERE game_id=?",
                              (game_id,)).fetchone()
        return (row["store"], row["code"]) if row else None


_SCHEMA_TABLES = ("works", "library_links")
