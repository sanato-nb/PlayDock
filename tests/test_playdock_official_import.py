"""Migration from historical PlayDock and scanner DBs to two unified tables.

All data is generated within tmp_path. No user's real data is touched.
"""
from pathlib import Path
import json
import sqlite3

from core import Game, Library
from database.work_repository import WorkDatabase, SCHEMA_VERSION
from services.official_work_service import official_metadata_for_game, official_info_rows
from controllers.library import LibraryControllerMixin
from data_management import backup_data, restore_data, inspect_backup


def legacy_scanner(path: Path):
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE official_works (
            store TEXT NOT NULL, product_id TEXT NOT NULL,
            official_title TEXT NOT NULL, category TEXT NOT NULL,
            page_url TEXT NOT NULL, verified_at_utc TEXT NOT NULL,
            PRIMARY KEY(store, product_id))""")
        con.executemany("INSERT INTO official_works VALUES (?,?,?,?,?,?)", [
            ("dlsite", "RJ123456", "일본어 공식 게임", "maniax",
             "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
             "2026-11-20T11:30:00+00:00"),
            ("steam", "1091500", "Steam Official Game", "game",
             "https://store.steampowered.com/app/1091500/",
             "2026-11-20T11:30:00+00:00"),
        ])
    return path


def legacy_v2(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE works (
                code TEXT PRIMARY KEY, fallback_title TEXT NOT NULL,
                maker TEXT NOT NULL DEFAULT '', release_date TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT '', retrieved_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE work_titles (
                code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                lang TEXT NOT NULL, title TEXT NOT NULL, PRIMARY KEY(code,lang));
            CREATE TABLE work_tags (
                code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                tag TEXT NOT NULL, PRIMARY KEY(code,tag));
            CREATE TABLE work_images (
                code TEXT NOT NULL REFERENCES works(code) ON DELETE CASCADE,
                kind TEXT NOT NULL, position INTEGER NOT NULL, url TEXT NOT NULL,
                PRIMARY KEY(code,kind,position));
            CREATE TABLE library_links (
                game_id TEXT PRIMARY KEY, raw_name TEXT NOT NULL,
                archive_name TEXT, product_code TEXT, last_seen TEXT NOT NULL);
            CREATE TABLE official_works (
                store TEXT NOT NULL, product_id TEXT NOT NULL,
                official_title TEXT NOT NULL, category TEXT NOT NULL,
                page_url TEXT NOT NULL, verified_at_utc TEXT NOT NULL,
                PRIMARY KEY(store,product_id));
            INSERT INTO works VALUES
                ('RJ123456','기존 사용자가 저장한 상세 제목','제작사','2024-07-01',
                 'https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html',
                 'https://www.dlsite.com/a','dlsite','2025-01-02');
            INSERT INTO work_titles VALUES ('RJ123456','ko','내가 저장한 한국어 제목');
            INSERT INTO work_titles VALUES ('RJ123456','ja','もとの名前');
            INSERT INTO work_tags VALUES ('RJ123456','RPG');
            INSERT INTO work_tags VALUES ('RJ123456','ADV');
            INSERT INTO work_images VALUES
                ('RJ123456','cover',0,'https://img.dlsite.jp/test.jpg');
            INSERT INTO official_works VALUES
                ('dlsite','RJ123456','서로 다른 공식 제목','maniax',
                 'https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html',
                 '2026-11-20T11:00:00+00:00');
            INSERT INTO official_works VALUES
                ('steam','1091500','Steam Official Game','game',
                 'https://store.steampowered.com/app/1091500/',
                 '2026-11-20T11:00:00+00:00');
            INSERT INTO library_links VALUES
                ('game_1','개인용 예제','RJ123456.zip','RJ123456','2026-11-20');
            PRAGMA user_version=2;
        """)
    return path


def test_v2_migrates_six_to_two_tables_and_preserves_detail(tmp_path):
    dbpath = legacy_v2(tmp_path / "data" / "playdock.db")
    db = WorkDatabase(dbpath.parent)
    with db.connect() as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"works", "library_links"}
        assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 3
        works_cols = {row[1] for row in con.execute("PRAGMA table_info(works)")}
        assert works_cols == {"store","code","title","category","maker","page_url",
                             "checked_at","titles_json","tags_json","images_json"}
        links_cols = {row[1] for row in con.execute("PRAGMA table_info(library_links)")}
        assert links_cols == {"game_id","store","code"}
        assert con.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 2
        assert tuple(con.execute("SELECT store,code FROM library_links").fetchone()) == (
            "dlsite", "RJ123456")
    detail = db.get_work("RJ123456")
    assert detail["title"] == "기존 사용자가 저장한 상세 제목"
    assert detail["maker"] == "제작사"
    assert detail["category"] == "maniax"
    assert detail["titles"] == {"ko": "내가 저장한 한국어 제목", "ja": "もとの名前"}
    assert set(detail["tags"]) == {"RPG", "ADV"}
    assert detail["images"][0]["kind"] == "cover"
    assert "release_date" not in detail
    assert db.get_official_work("steam", "1091500")["title"] == "Steam Official Game"
    backups = list((dbpath.parent / "backups").glob("playdock_pre_v3_*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as old:
        assert old.execute("PRAGMA user_version").fetchone()[0] == 2
        assert old.execute("SELECT release_date FROM works").fetchone()[0] == "2024-07-01"
        assert old.execute("SELECT COUNT(*) FROM work_images").fetchone()[0] == 1
    # Reopen does not re-migrate or create a new snapshot.
    WorkDatabase(dbpath.parent)
    assert len(list((dbpath.parent / "backups").glob("playdock_pre_v3_*.db"))) == 1


def test_legacy_scanner_imports_into_main_without_other_db_writes(tmp_path):
    source = legacy_scanner(tmp_path / "official_works.sqlite3")
    original = source.read_bytes()
    db = WorkDatabase(tmp_path / "data")
    assert db.import_scanner_catalog(source) == 2
    assert db.count_works() == 2
    assert db.count_official_works() == 2
    assert db.import_scanner_catalog(source) == 2
    assert db.count_works() == 2
    assert source.read_bytes() == original
    steam = db.get_official_work("steam", "1091500")
    assert steam["title"] == "Steam Official Game"
    assert dict(official_info_rows(steam))["공식 작품 종류·분류"] == "game"


def test_one_time_legacy_scanner_auto_import_from_old_location(tmp_path, monkeypatch):
    source = legacy_scanner(tmp_path / "historical.sqlite3")
    monkeypatch.setenv("PLAYDOCK_OFFICIAL_CATALOG_PATH", str(source))
    db = WorkDatabase(tmp_path / "data", import_legacy=True)
    assert db.count_works() == 2
    assert db.get_official_work("dlsite", "RJ123456") is not None
    with db.connect() as con:
        first_marker = con.execute("PRAGMA application_id").fetchone()[0]
        assert first_marker != 0
    WorkDatabase(tmp_path / "data", import_legacy=True)
    assert db.count_works() == 2
    assert source.exists()


def test_v1_migration_keeps_user_title_and_url(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    dbpath = data / "playdock.db"
    with sqlite3.connect(dbpath) as conn:
        conn.executescript("""
            CREATE TABLE works (code TEXT PRIMARY KEY,
                fallback_title TEXT NOT NULL, maker TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '', page_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE library_links (
                game_id TEXT PRIMARY KEY, raw_name TEXT NOT NULL,
                archive_name TEXT, product_code TEXT, last_seen TEXT NOT NULL);
            INSERT INTO works(code, fallback_title)
                VALUES('RJ654321', '사용자가 저장한 제목');
            PRAGMA user_version=1;
        """)
    db = WorkDatabase(data)
    assert db.get_work("RJ654321")["title"] == "사용자가 저장한 제목"
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3


def test_library_uses_site_marker_but_never_infers_unmarked_steam_id(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    db.import_scanner_catalog(legacy_scanner(tmp_path / "old.sqlite3"))
    lib = Library(tmp_path / "settings")
    root = tmp_path / "archives"
    root.mkdir()
    dlzip = root / "Original [RJ123456].zip"
    dlzip.write_bytes(b"unchanged contents")
    dl = Game("g1", dlzip.stem, root, archive=dlzip)
    steam = Game("g2", "Other Name [Steam 1091500]", root)
    number = Game("g3", "Game build 1091500", root)
    assert official_metadata_for_game(lib, dl, db)["store"] == "dlsite"
    assert official_metadata_for_game(lib, steam, db)["store"] == "steam"
    assert official_metadata_for_game(lib, number, db) is None
    lib.update_meta(dl, title="사용자 이름", prefer_manual_title=True)
    assert db.import_scanner_catalog(tmp_path / "old.sqlite3") == 2
    assert "사용자 이름" in lib.title(dl)
    lib.update_meta(steam, product_code="")
    assert official_metadata_for_game(lib, steam, db) is None
    assert dlzip.read_bytes() == b"unchanged contents"


def test_no_unverified_legacy_site_urls_imported(tmp_path):
    source = legacy_scanner(tmp_path / "legacy.sqlite3")
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO official_works VALUES(?,?,?,?,?,?)",
                    ("steam","12345678","Fake","game",
                     "https://evil.example/app/12345678/","2026-11-20"))
    db = WorkDatabase(tmp_path / "data")
    assert db.import_scanner_catalog(source) == 2
    assert db.get_work("12345678", store="steam") is None


def test_missing_legacy_catalog_does_not_create_file(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    source = tmp_path / "missing.sqlite3"
    assert db.import_scanner_catalog(source) == 0
    assert not source.exists()


def test_imported_works_survive_playdock_zip_backup_restore(tmp_path):
    source = legacy_scanner(tmp_path / "scan.sqlite3")
    data = tmp_path / "data"
    db = WorkDatabase(data)
    assert db.import_scanner_catalog(source) == 2
    backup = tmp_path / "backup.zip"
    backup_data(data, [], backup)
    assert "playdock.db" in inspect_backup(backup)
    with db.connect() as con:
        con.execute("DELETE FROM works")
    assert db.count_works() == 0
    restore_data(data, backup)
    assert db.count_works() == 2


def test_launcher_info_rows_show_one_unified_official_record(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    db.import_scanner_catalog(legacy_scanner(tmp_path / "scan.sqlite3"))
    lib = Library(tmp_path / "settings")
    game = Game("steam", "Steam 1091500", tmp_path)
    ctrl = type("Fake", (LibraryControllerMixin,), {})()
    ctrl.library = lib
    ctrl.work_db = db
    rows = dict(ctrl.work_db_info_rows(game))
    assert rows["공식 작품명"] == "Steam Official Game"
    assert rows["공식 판매처"] == "Steam"
    assert "발매일" not in rows
    assert len(rows) == len(set(rows))
