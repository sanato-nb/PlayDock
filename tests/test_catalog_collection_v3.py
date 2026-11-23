"""Collect work metadata in batch before identity/rename, without touching games."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from core import Library, Game
from database.work_repository import WorkDatabase
from experiments.dlsite_detector.code_only import Work, Result, codes_in, steam_ids_in
from services.catalog_collection_service import (
    CatalogEntry, CatalogEvent, CatalogCollector, collect_batch,
    game_catalog_entries, entry_input,
)
from services.title_workers import _db_title, BulkTitleWorker, TitleWorker
from services.identity_artwork_worker import IdentityArtworkThread
from ui.dialogs.catalog_collection import CatalogCollectionDialog


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


DL_URL = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
ST_URL = "https://store.steampowered.com/app/1091500/"
DL_IMG = "https://img.dlsite.jp/cover.jpg"
ST_IMG = "https://cdn.akamai.steamstatic.com/steam/apps/1091500/header.jpg"


def fake_detail(code):
    assert code == "RJ123456"
    return {
        "code": code, "fallback_title": "공식 일본어 제목",
        "titles": {"ko": "공식 한국어 제목", "ja": "日本語タイトル"},
        "maker": "공식 개발사", "page_url": DL_URL,
        "tags": ["RPG"], "images": [
            {"kind": "cover", "position": 0, "url": DL_IMG},
        ]
    }


def fake_checker(calls):
    def check(input_item, *, cache):
        code = codes_in(input_item.label)
        steam = steam_ids_in(input_item.label)
        if code:
            key = code[0]
            if key in cache:
                result = cache[key]
            else:
                calls.append("DLsite:" + key)
                result = Work(key, "공식 일본어 제목", "maniax",
                              DL_URL, "verified", "dlsite")
                cache[key] = result
        elif steam:
            key = "STEAM:" + steam[0]
            if key in cache:
                result = cache[key]
            else:
                calls.append(key)
                result = Work(steam[0], "Steam Official", "game",
                              ST_URL, "verified", "steam")
                cache[key] = result
        else:
            return Result(input_item.label, input_item.origin, "excluded")
        return Result(input_item.label, input_item.origin, "confirmed",
                      (result,), selected_store=result.store)
    return check


def test_collect_new_and_cached_without_requery(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    calls = []
    details = []
    def detail(code):
        details.append(code)
        return fake_detail(code)
    collector = CatalogCollector(db, checker=fake_checker(calls),
                                 dlsite_detail=detail)
    entries = [
        CatalogEntry("g1", "A [RJ123456].7z"),
        CatalogEntry("g2", "Duplicate [RJ123456].zip"),
    ]
    events = [collector.collect_one(e) for e in entries]
    assert [e.outcome for e in events] == ["fetched", "cached"]
    assert calls == ["DLsite:RJ123456"]
    assert details == ["RJ123456"]
    assert db.count_works() == 1
    stored = db.get_work("RJ123456")
    assert stored["titles"]["ko"] == "공식 한국어 제목"
    assert stored["maker"] == "공식 개발사"
    assert {"hero", "icon"}.issubset({x["kind"] for x in stored["images"]})
    assert "release_date" not in stored
    next_batch = CatalogCollector(db, checker=fake_checker(calls),
                                  dlsite_detail=detail)
    assert next_batch.collect_one(entries[0]).outcome == "cached"
    assert calls == ["DLsite:RJ123456"] and details == ["RJ123456"]


def test_collect_steam_from_marked_appid_and_persist_art_urls(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    calls = []
    collector = CatalogCollector(
        db, checker=fake_checker(calls),
        steam_art=lambda app_id: {"hero": ST_IMG, "icon": ST_IMG})
    event = collector.collect_one(CatalogEntry("steam", "Game [Steam 1091500].rar"))
    assert event.outcome == "fetched"
    assert calls == ["STEAM:1091500"]
    record = db.get_official_work("steam", "1091500")
    assert record["title"] == "Steam Official"
    assert len(record["images"]) == 2
    assert not list(tmp_path.rglob("hero.png"))
    assert not list(tmp_path.rglob("icon.png"))


def test_no_code_manual_clear_and_uncertain_id_never_contact_web(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    calls = []
    collector = CatalogCollector(db, checker=fake_checker(calls))
    for entry in (
        CatalogEntry("n1", "Game 1091500 build", "archive"),
        CatalogEntry("n2", "Has code [RJ123456].zip", "archive",
                     suppress_code=True),
    ):
        assert collector.collect_one(entry).outcome == "skipped"
    assert calls == [] and db.count_works() == 0


def test_collect_batch_counts_progress_and_interrupts_after_first(tmp_path):
    db = WorkDatabase(tmp_path / "data")
    calls = []
    collector = CatalogCollector(db, checker=fake_checker(calls),
                                 dlsite_detail=fake_detail)
    progress = []
    entries = [
        CatalogEntry("1", "Game [RJ123456].zip"),
        CatalogEntry("2", "Other [Steam 1091500].zip"),
    ]
    result = collect_batch(
        entries, db.path,
        collector_factory=lambda db_arg: collector,
        callback=lambda i, total, item: progress.append((i, total, item.outcome)),
        is_cancelled=lambda: bool(progress),
    )
    assert len(result) == 1
    assert progress == [(1, 2, "fetched")]
    assert db.count_works() == 1


def test_no_path_or_manual_title_sent_to_checker(tmp_path):
    lib = Library(tmp_path / "data")
    root = tmp_path / "Private"
    root.mkdir()
    archive = root / "Official [RJ123456].zip"
    archive.write_bytes(b"unchanged archive")
    game = Game("g", "Original [RJ123456]", root, archive=archive)
    lib.update_meta(game, title="비공개 사용자가 정한 표시 이름")
    entries = game_catalog_entries(lib, [game])
    assert len(entries) == 1
    assert entries[0].label == archive.name
    assert "Private" not in entry_input(entries[0]).label
    assert "비공개" not in entry_input(entries[0]).label
    assert archive.read_bytes() == b"unchanged archive"


def test_bulk_titles_consume_db_first_and_never_fake_korean(tmp_path, monkeypatch):
    from services import title_workers
    db = WorkDatabase(tmp_path / "data")
    db.save_work(fake_detail("RJ123456"))
    title, source, language = _db_title(
        "RJ123456", "ko", tmp_path / "data" / "localized_product_titles.json")
    assert (title, language) == ("공식 한국어 제목", "ko")
    assert "DB" in source
    def crash_if_called(*a, **kw):
        raise AssertionError("Existing DB row must prevent web name lookup")
    monkeypatch.setattr(title_workers, "lookup_localized_title", crash_if_called)
    worker = BulkTitleWorker(
        [("g", "Original [RJ123456]", "RJ123456")], "ko",
        tmp_path / "data" / "localized_product_titles.json")
    results = []
    worker.complete.connect(results.append)
    worker.run()
    assert results[0][0]["title"] == "공식 한국어 제목"
    assert results[0][0]["language"] == "ko"
    with db.connect() as conn:
        conn.execute("UPDATE works SET titles_json='{}' WHERE store='dlsite'")
    result = _db_title("RJ123456", "ko",
                       tmp_path / "data" / "localized_product_titles.json")
    assert result[2] == "ja", "Do not claim unknown Korean title is Korean"


def test_cached_identity_thread_uses_db_for_website_verification(
        tmp_path, monkeypatch):
    from services import identity_artwork_worker as module
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([{
        "store": "steam", "code": "1091500", "title": "Saved official",
        "category": "game", "page_url": ST_URL,
    }])
    db.save_official_image_urls("steam", "1091500", {"hero": ST_IMG})
    received = []
    def check_from_cache(item, *, cache):
        assert cache["STEAM:1091500"].title == "Saved official"
        work = cache["STEAM:1091500"]
        return Result(item.label, item.origin, "confirmed", (work,),
                      selected_store="steam")
    monkeypatch.setattr(module, "check", check_from_cache)
    def prepare(work, *, candidates):
        assert candidates == {"hero": ST_IMG}
        return {}
    monkeypatch.setattr(module, "prepare_official_images", prepare)
    worker = IdentityArtworkThread("Game [Steam 1091500]", db_path=db.path)
    worker.complete.connect(lambda *args: received.append(args))
    worker.run()
    assert received and received[0][1].code == "1091500"


def test_progress_dialog_reports_errors_without_modifying_files(app, tmp_path):
    dialog = CatalogCollectionDialog(3)
    cancelled = []
    dialog.cancelRequested.connect(lambda: cancelled.append(True))
    try:
        dialog.on_progress(1, 3, CatalogEvent("g1", "One.zip", "fetched", "ok", 1))
        dialog.on_progress(2, 3, CatalogEvent("g2", "Second.zip", "skipped", "품번 없음"))
        assert dialog.progress.value() == 2
        assert "Second.zip" in dialog.failures.toPlainText()
        dialog.request_cancel()
        assert cancelled == [True]
        dialog.on_complete([], interrupted=True)
        assert dialog.close_button.isEnabled()
        assert not dialog.running
    finally:
        dialog.close()


def test_ui_places_collection_before_identity_and_removes_web_image_search():
    repo = Path(__file__).resolve().parents[1]
    layout = (repo / "src/playdock/ui/launcher_layout.py").read_text("utf-8")
    meta = (repo / "src/playdock/controllers/metadata.py").read_text("utf-8")
    assert layout.index('"게임 정보 수집"') < layout.index('"게임 정체 판독"')
    assert "인터넷 이미지 검색·편집" not in layout
    assert "open_online_artwork" not in layout
    assert "def open_online_artwork" not in meta
    assert "온라인 이미지 검색" not in layout
    assert "이미지 직접 지정" in layout


def test_steam_name_preview_uses_unified_db_without_web(tmp_path, monkeypatch):
    from services import title_workers
    from services.bulk_title_service import BulkTitleActions
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([{
        "store": "steam", "code": "1091500", "title": "Steam 정식 작품명",
        "category": "game", "page_url": ST_URL,
    }])
    monkeypatch.setattr(title_workers, "lookup_localized_title",
                        lambda *args: (_ for _ in ()).throw(
                            AssertionError("Steam lookup must not use DLsite lookup")))
    worker = BulkTitleWorker(
        [("steam-id", "Local [Steam 1091500]", "1091500", "steam")],
        "ko", tmp_path / "data" / "localized_product_titles.json")
    responses = []
    worker.complete.connect(responses.append)
    worker.run()
    record = responses[0][0]
    assert record["title"] == "Steam 정식 작품명"
    assert record["store"] == "steam"
    assert record["language"] == "en"
    library = Library(tmp_path / "data")
    game = Game("steam-id", "Local [Steam 1091500]", tmp_path)
    previews = BulkTitleActions(library).lookup_preview(
        [game], responses[0], "ko", save_as_localized=True)
    assert len(previews) == 1
    assert previews[0].method == "manual"
    assert not previews[0].product_code
