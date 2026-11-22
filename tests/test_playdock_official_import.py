"""Offline integration: scanner's public metadata -> PlayDock's own database."""
from pathlib import Path
import sqlite3

from core import Game, Library
from database.work_repository import WorkDatabase
from database.official_catalog import OfficialWorkCatalog
from experiments.dlsite_detector.code_only import Result, Work
from services.official_work_service import official_metadata_for_game, official_info_rows
from controllers.library import LibraryControllerMixin
from data_management import backup_data, restore_data, inspect_backup


def make_scanner_database(path):
    scanner = OfficialWorkCatalog(path)
    records = [
        Result("RJ123456.zip", "archive", "confirmed", (
            Work("RJ123456", "일본어 공식 게임", "maniax",
                 "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                 "verified", "dlsite"),), selected_store="dlsite"),
        Result("Steam 1091500.zip", "archive", "confirmed", (
            Work("1091500", "Steam Official Game", "game",
                 "https://store.steampowered.com/app/1091500/",
                 "verified", "steam"),), selected_store="steam"),
    ]
    assert scanner.save_verified_results(records) == 2
    return scanner


def test_import_both_stores_preserves_scanner_db(tmp_path):
    source = make_scanner_database(tmp_path / "scanner.sqlite3")
    before = source.path.read_bytes()
    db = WorkDatabase(tmp_path / "data")
    assert db.import_scanner_catalog(source.path) == 2
    assert db.count_official_works() == 2
    assert source.path.read_bytes() == before
    assert db.get_official_work("dlsite", "rj123456")["official_title"] == "일본어 공식 게임"
    assert db.get_official_work("steam", "1091500")["category"] == "game"
    assert db.import_scanner_catalog(source.path) == 2
    assert db.count_official_works() == 2
    assert db.count_works() == 0


def test_existing_v1_database_upgrade_preserves_user_work(tmp_path):
    store = tmp_path / "data"
    store.mkdir()
    path = store / "playdock.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE works (
                code TEXT PRIMARY KEY,
                fallback_title TEXT NOT NULL,
                maker TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE library_links (
                game_id TEXT PRIMARY KEY, raw_name TEXT NOT NULL,
                archive_name TEXT, product_code TEXT, last_seen TEXT NOT NULL
            );
            INSERT INTO works(code, fallback_title)
                VALUES('RJ654321', '사용자가 저장한 제목');
            PRAGMA user_version=1;
        """)
    db = WorkDatabase(store)
    assert db.get_work("RJ654321")["fallback_title"] == "사용자가 저장한 제목"
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    source = make_scanner_database(tmp_path / "scanner.sqlite3")
    assert db.import_scanner_catalog(source.path) == 2
    assert db.get_work("RJ654321")["fallback_title"] == "사용자가 저장한 제목"


def test_match_dlsite_and_marked_steam_without_editing_game_files(tmp_path):
    source = make_scanner_database(tmp_path / "scanner.sqlite3")
    db = WorkDatabase(tmp_path / "data")
    db.import_scanner_catalog(source.path)
    library = Library(tmp_path / "settings")
    archive = tmp_path / "RJ123456.zip"
    archive.write_bytes(b"untouched")
    dl = Game("dl", "Local [RJ123456]", tmp_path, archive=archive)
    steam = Game("steam", "Other [Steam 1091500]", tmp_path)
    assert official_metadata_for_game(library, dl, db)["store"] == "dlsite"
    record = official_metadata_for_game(library, steam, db)
    assert record["store"] == "steam"
    assert dict(official_info_rows(record))["공식 작품 종류·분류"] == "game"
    library.update_meta(dl, title="내가 정한 이름", prefer_manual_title=True)
    assert db.import_scanner_catalog(source.path) == 2
    assert "내가 정한 이름" in library.title(dl)
    assert archive.read_bytes() == b"untouched"


def test_no_guess_for_unmarked_steam_numbers_and_explicit_unlink(tmp_path):
    db = WorkDatabase(tmp_path / "db")
    db.import_scanner_catalog(make_scanner_database(tmp_path / "scanner.sqlite3").path)
    library = Library(tmp_path / "settings")
    random_number = Game("a", "Game build 1091500", tmp_path)
    assert official_metadata_for_game(library, random_number, db) is None
    link = Game("b", "Game [RJ123456] [Steam 1091500]", tmp_path)
    library.update_meta(link, product_code="")
    assert official_metadata_for_game(library, link, db) is None


def test_missing_source_doesnt_create_db(tmp_path):
    db = WorkDatabase(tmp_path / "db")
    path = tmp_path / "missing.sqlite3"
    assert db.import_scanner_catalog(path) == 0
    assert not path.exists()
    assert db.count_official_works() == 0


def test_invalid_source_rows_do_not_override_verified(tmp_path):
    source = make_scanner_database(tmp_path / "scan.sqlite3")
    with sqlite3.connect(source.path) as conn:
        conn.execute("INSERT INTO official_works VALUES(?,?,?,?,?,?)",
                     ("steam", "12345678", "Fake", "game",
                      "https://evil.example/app/12345678/", "2026-11-22"))
    db = WorkDatabase(tmp_path / "db")
    assert db.import_scanner_catalog(source.path) == 2
    assert db.get_official_work("steam", "12345678") is None


def test_imported_data_survives_playdock_backup_restore(tmp_path):
    source = make_scanner_database(tmp_path / "scan.sqlite3")
    store = tmp_path / "data"
    db = WorkDatabase(store)
    assert db.import_scanner_catalog(source.path) == 2
    backup = tmp_path / "backup.zip"
    backup_data(store, [], backup)
    assert "playdock.db" in inspect_backup(backup)
    with db.connect() as conn:
        conn.execute("DELETE FROM official_works")
    assert db.count_official_works() == 0
    restore_data(store, backup)
    assert db.count_official_works() == 2


def test_launcher_detail_rows_show_imported_steam_without_legacy_db(tmp_path):
    source = make_scanner_database(tmp_path / "scan.sqlite3")
    db = WorkDatabase(tmp_path / "data")
    db.import_scanner_catalog(source.path)
    library = Library(tmp_path / "settings")
    game = Game("steam", "Steam 1091500", tmp_path)
    controller = type("NoUi", (LibraryControllerMixin,), {})()
    controller.library = library
    controller.work_db = db
    values = dict(controller.work_db_info_rows(game))
    assert values["공식 작품명"] == "Steam Official Game"
    assert values["공식 판매처"] == "Steam"
    assert values["공식 작품 페이지"] == "https://store.steampowered.com/app/1091500/"


def test_default_scanner_location_used_by_main_app(tmp_path, monkeypatch):
    source = make_scanner_database(tmp_path / "scanner.sqlite3")
    monkeypatch.setenv("PLAYDOCK_OFFICIAL_CATALOG_PATH", str(source.path))
    db = WorkDatabase(tmp_path / "data")
    assert db.import_scanner_catalog() == 2
