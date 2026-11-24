"""B-location: installed PlayDock/data/playdock.db is the sole active catalog.

The test uses fake archives and a verified local installation marker.
"""
from pathlib import Path
import sqlite3

from database.official_catalog import (
    OfficialWorkCatalog, default_catalog_path, installed_database_path,
    legacy_catalog_path, remember_install_folder,
)
from database.work_repository import WorkDatabase
from experiments.dlsite_detector.code_only import Result, Work
from experiments.dlsite_detector.scan_handoff import ScanReport
from storage.local import write_install_marker
from scripts import scan_then_prompt


def _result():
    work = Work(
        "RJ123456", "공식 확인 작품", "maniax",
        "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
        "verified", "dlsite")
    return Result("RJ123456.zip", "archive", "confirmed",
                  (work,), selected_store="dlsite")


def _installed(tmp_path):
    root = tmp_path / "Installed-PlayDock"
    root.mkdir()
    write_install_marker(root)
    return root


def test_install_marker_required_and_legacy_is_only_migration_input(tmp_path, monkeypatch):
    root = tmp_path / "not_install"
    root.mkdir()
    assert installed_database_path(root) is None
    assert not (root / "data").exists()
    installed = _installed(tmp_path)
    assert installed_database_path(installed) == installed / "data" / "playdock.db"
    monkeypatch.setenv("PLAYDOCK_INSTALL_DIR", str(installed))
    assert default_catalog_path() == installed / "data" / "playdock.db"
    assert not (installed / "data").exists()


def test_remembered_install_folder_points_to_only_db(tmp_path, monkeypatch):
    installed = _installed(tmp_path)
    monkeypatch.delenv("PLAYDOCK_DB_PATH", raising=False)
    monkeypatch.delenv("PLAYDOCK_INSTALL_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "user_data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user_data"))
    path = remember_install_folder(installed)
    assert path == installed / "data" / "playdock.db"
    assert default_catalog_path() == path
    assert not path.exists()
    assert len(list((tmp_path / "user_data").rglob("*.sqlite3"))) == 0
    assert not legacy_catalog_path().exists()


def test_shared_scanner_and_main_write_the_same_works_table(tmp_path, monkeypatch):
    installed = _installed(tmp_path)
    monkeypatch.setenv("PLAYDOCK_INSTALL_DIR", str(installed))
    dbpath = default_catalog_path()
    assert dbpath is not None
    scanner = OfficialWorkCatalog()
    assert scanner.save_verified_results([_result()]) == 1
    assert scanner.path == dbpath
    assert scanner.get_work("dlsite", "RJ123456")["title"] == "공식 확인 작품"
    main = WorkDatabase(dbpath.parent)
    assert main.get_official_work("dlsite", "RJ123456")["title"] == "공식 확인 작품"
    with sqlite3.connect(dbpath) as con:
        assert {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")} == {
            "works", "library_links"}
    assert len(list(installed.rglob("*.db"))) == 1


def test_no_valid_install_never_creates_second_db(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "userdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "userdata"))
    monkeypatch.delenv("PLAYDOCK_DB_PATH", raising=False)
    monkeypatch.delenv("PLAYDOCK_INSTALL_DIR", raising=False)
    assert default_catalog_path() is None
    scanner = OfficialWorkCatalog()
    try:
        scanner.save_verified_results([_result()])
        raise AssertionError("A valid official work must not cause a fallback SQLite DB")
    except FileNotFoundError:
        pass
    assert not list(tmp_path.rglob("*.db"))
    assert not list(tmp_path.rglob("*.sqlite3"))


def test_failed_lookup_does_not_create_install_data_folder(tmp_path, monkeypatch):
    installed = _installed(tmp_path)
    monkeypatch.setenv("PLAYDOCK_INSTALL_DIR", str(installed))
    scanner = OfficialWorkCatalog()
    rejected = Work("RJ123456", "", "", "", "unavailable", "dlsite")
    result = Result("RJ123456.zip", "archive", "excluded",
                    (rejected,), selected_store="")
    assert scanner.save_verified_results([result]) == 0
    assert not (installed / "data").exists()


def test_cli_selected_install_folder_before_verified_scan(tmp_path, monkeypatch):
    installed = _installed(tmp_path)
    archives = tmp_path / "archives"
    archives.mkdir()
    archive = archives / "RJ123456.zip"
    archive.write_bytes(b"opaque fake archive data")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "user_data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user_data"))
    monkeypatch.delenv("PLAYDOCK_INSTALL_DIR", raising=False)
    monkeypatch.delenv("PLAYDOCK_DB_PATH", raising=False)
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **kw:
                        ScanReport((_result(),), 1))
    monkeypatch.setattr("builtins.input", lambda prompt="": "Y")
    assert scan_then_prompt.main([str(archives), "--playdock-folder",
                                  str(installed), "--output", str(tmp_path / "out")]) == 0
    dbpath = installed / "data" / "playdock.db"
    assert dbpath.is_file()
    assert WorkDatabase(dbpath.parent).get_work("RJ123456") is not None
    assert archive.read_bytes() == b"opaque fake archive data"
    assert not list((tmp_path / "user_data").rglob("*.sqlite3"))
    assert len(list((tmp_path / "out").rglob("*.txt"))) == 1
