"""The scanner's reusable official metadata DB uses fake works only."""
from pathlib import Path
import sqlite3

from experiments.dlsite_detector.code_only import Result, Work
from experiments.dlsite_detector.scan_handoff import ScanReport
from src.playdock.database.official_catalog import (
    OfficialWorkCatalog, default_catalog_path,
)
from scripts import scan_then_prompt


def _result(*works, status="confirmed"):
    return Result("private archive name.zip", "archive", status, works=tuple(works))


def test_catalog_persists_both_stores_and_categories(tmp_path):
    folder = tmp_path / "works.sqlite3"
    db = OfficialWorkCatalog(folder)
    results = [
        _result(Work("RJ01234567", "공식 DL 작품", "maniax",
                     "https://www.dlsite.com/maniax/work/=/product_id/RJ01234567.html",
                     "verified", "dlsite")),
        _result(Work("1091500", "Steam Official Name", "game",
                     "https://store.steampowered.com/app/1091500/",
                     "verified", "steam")),
    ]
    assert db.save_verified_results(results) == 2
    dl = db.get_work("dlsite", "rj01234567")
    assert dl["official_title"] == "공식 DL 작품"
    assert dl["category"] == "maniax"
    assert dl["page_url"].endswith("RJ01234567.html")
    assert dl["store"] == "dlsite" and dl["product_id"] == "RJ01234567"
    assert dl["verified_at_utc"]
    steam = db.get_work("steam", "1091500")
    assert steam["official_title"] == "Steam Official Name"
    assert steam["category"] == "game"
    with sqlite3.connect(folder) as con:
        assert con.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 2
        assert "private archive name.zip" not in str(con.execute(
            "SELECT * FROM works").fetchall())


def test_catalog_deduplicates_and_updates_without_erasing_on_failure(tmp_path):
    db = OfficialWorkCatalog(tmp_path / "catalog.sqlite3")
    old = Work("RJ123456", "First", "maniax",
               "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
               "verified", "dlsite")
    new = Work("RJ123456", "Updated", "books",
               old.url, "verified", "dlsite")
    failed = Work("RJ123456", "", "", "", "unavailable", "dlsite")
    assert db.save_verified_results([_result(old), _result(new)]) == 1
    assert db.get_work("dlsite", "RJ123456")["official_title"] == "Updated"
    assert db.save_verified_results([_result(failed, status="excluded")]) == 0
    assert db.get_work("dlsite", "RJ123456")["official_title"] == "Updated"


def test_catalog_rejects_unverified_or_untrusted_urls(tmp_path):
    path = tmp_path / "no_created.sqlite3"
    db = OfficialWorkCatalog(path)
    assert db.get_work("dlsite", "RJ123456") is None
    assert db.save_verified_results([
        _result(Work("RJ123456", "No", "maniax",
                     "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                     "unavailable", "dlsite")),
        _result(Work("1091500", "Spoof", "game",
                     "https://notsteam.example/app/1091500/",
                     "verified", "steam")),
    ]) == 0
    assert not path.exists()


def test_catalog_saves_verified_row_from_partial_scan(tmp_path):
    db = OfficialWorkCatalog(tmp_path / "catalog.sqlite3")
    works = [
        Work("RJ123456", "Verified", "maniax",
             "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
             "verified", "dlsite"),
        Work("RJ654321", "", "", "", "unavailable", "dlsite"),
    ]
    assert db.save_verified_results([_result(*works, status="partial")]) == 1
    assert db.get_work("dlsite", "RJ123456") is not None
    assert db.get_work("dlsite", "RJ654321") is None


def test_default_location_can_be_isolated_without_user_data(tmp_path, monkeypatch):
    path = tmp_path / "safe_test_catalog.sqlite3"
    monkeypatch.setenv("PLAYDOCK_DB_PATH", str(path))
    assert default_catalog_path() == path
    assert not path.exists()


def test_scanner_saves_catalog_after_successful_txt(tmp_path, monkeypatch):
    target = tmp_path / "scanner_catalog.sqlite3"
    monkeypatch.setenv("PLAYDOCK_DB_PATH", str(target))
    source = tmp_path / "archives"
    source.mkdir()
    archive = source / "Fake [RJ123456].zip"
    archive.write_bytes(b"fake archive unmodified")
    work = Work("RJ123456", "Stored Game", "maniax",
                "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                "verified", "dlsite")
    report = ScanReport((_result(work),), 1)
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **kw: report)
    output_dir = tmp_path / "output"
    result = scan_then_prompt.run(source, output_dir=output_dir)
    assert result == 0
    assert target.is_file()
    assert OfficialWorkCatalog(target).get_work("dlsite", "RJ123456")["official_title"] == "Stored Game"
    assert archive.read_bytes() == b"fake archive unmodified"


def test_scanner_still_succeeds_if_catalog_unwritable(tmp_path, monkeypatch):
    source = tmp_path / "games"
    source.mkdir()
    (source / "Fake [RJ123456].zip").write_bytes(b"untouched")
    monkeypatch.setenv("PLAYDOCK_DB_PATH", str(tmp_path))
    work = Work("RJ123456", "Stored Game", "maniax",
                "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                "verified", "dlsite")
    monkeypatch.setattr(scan_then_prompt, "scan_folder", lambda *a, **kw:
                        ScanReport((_result(work),), 1))
    assert scan_then_prompt.run(source, output_dir=tmp_path / "out") == 0
    assert list((tmp_path / "out").rglob("*.txt"))
