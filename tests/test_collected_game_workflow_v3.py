"""DB-first PlayDock flow: collect/identify -> choose artwork or official title.

Local fake archives and stubbed network. No user's files or website calls.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from core import Game, Library
from database.work_repository import WorkDatabase
from experiments.dlsite_detector.code_only import InputItem, Work, Result
from services.catalog_collection_service import CatalogEntry, CatalogCollector
from services.identity_artwork_worker import IdentityArtworkThread
from services.bulk_title_service import BulkTitleActions
from services.title_workers import BulkTitleWorker
from simple_title_edit import save_display_title, restore_filename_title
from controllers.metadata import MetadataControllerMixin


URL = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
IMAGE = "https://img.dlsite.jp/cover.jpg"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def fake_checker(entry: InputItem, *, cache):
    work = Work("RJ123456", "확인된 공식 게임명", "maniax",
                URL, "verified", "dlsite")
    return Result(entry.label, entry.origin, "confirmed", (work,),
                  selected_store="dlsite")


def detail(_code):
    return {"code": "RJ123456",
            "fallback_title": "확인된 공식 게임명",
            "titles": {"ja": "公式タイトル", "ko": "공식 한국어 제목"},
            "maker": "테스트 제작사",
            "page_url": URL,
            "tags": ["RPG"],
            "images": [{"kind": "cover", "position": 0, "url": IMAGE}]}


def test_collected_game_links_to_works_and_survives_refresh(tmp_path):
    library = Library(tmp_path / "data")
    archive = tmp_path / "Game [RJ123456].zip"
    archive.write_bytes(b"TEST-COMPRESSED-ARCHIVE-BYTES")
    game = Game("game", archive.stem, tmp_path, archive=archive)
    db = WorkDatabase(library.store)
    collector = CatalogCollector(
        db, checker=fake_checker, dlsite_detail=detail,
    )
    event = collector.collect_one(CatalogEntry(game.id, archive.name))
    assert event.outcome == "fetched"
    assert event.connected
    assert (event.store, event.code) == ("dlsite", "RJ123456")
    assert db.get_link(game.id) == ("dlsite", "RJ123456")
    assert db.get_official_work("dlsite", "RJ123456")["title"]
    # Refresh must NOT delete links that were automatically confirmed.
    db.sync_library(library, [game])
    assert db.get_link(game.id) == ("dlsite", "RJ123456")
    assert archive.read_bytes() == b"TEST-COMPRESSED-ARCHIVE-BYTES"
    assert not (library.art_dir(game) / "icon.png").exists()


def test_works_row_alone_does_not_unlock_uncollected_game(tmp_path):
    library = Library(tmp_path / "data")
    game = Game("uncollected", "Any [RJ123456]", tmp_path)
    db = WorkDatabase(library.store)
    db._upsert_verified([{
        "store": "dlsite", "code": "RJ123456",
        "title": "공식 작품명", "page_url": URL,
    }])
    class Stub(MetadataControllerMixin):
        def __init__(self):
            self.library = library
            self.work_db = db
            self.games = [game]
        def current(self):
            return game
    stub = Stub()
    assert not stub.has_collected_game_info()
    assert stub.collected_game_record(game) is None
    # The same officially verified work becomes usable ONLY after collection
    # has explicitly associated it with this local game.
    assert db.save_verified_game_link(game.id, "dlsite", "RJ123456")
    assert stub.has_collected_game_info()
    assert stub.collected_game_record()["code"] == "RJ123456"
    # Manual "clear product ID" is a deliberate revocation.
    library.update_meta(game, product_code="")
    assert not stub.has_collected_game_info()
    db.sync_library(library, [game])
    assert db.get_link(game.id) is None


def test_image_only_mode_never_runs_identity_search(tmp_path, monkeypatch):
    from services import identity_artwork_worker as module
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([{
        "store": "dlsite", "code": "RJ123456",
        "title": "공식 게임명", "page_url": URL,
    }])
    db.save_official_image_urls(
        "dlsite", "RJ123456", {"hero": IMAGE, "icon": IMAGE})
    work = Work("RJ123456", "공식 게임명", "maniax",
                URL, "verified", "dlsite")
    def no_identity_scan(*args, **kw):
        raise AssertionError("image settings must not re-identify the game")
    monkeypatch.setattr(module, "check", no_identity_scan)
    images_requested = []
    def load_preview(*args, **kwargs):
        images_requested.append(kwargs.get("candidates"))
        return {"hero": object()}
    monkeypatch.setattr(module, "prepare_official_images", load_preview)
    worker = IdentityArtworkThread("Game [RJ123456].zip",
                                  db_path=db.path, verified_work=work)
    responses = []
    worker.complete.connect(lambda *args: responses.append(args))
    worker.run()
    assert responses and responses[0][1] == work
    assert set(responses[0][2]) == {"hero"}
    assert images_requested[0] == {"hero": IMAGE, "icon": IMAGE}


def test_official_title_uses_collected_db_not_web(tmp_path, monkeypatch):
    from services import title_workers
    db = WorkDatabase(tmp_path / "data")
    db._upsert_verified([{
        "store": "dlsite", "code": "RJ123456",
        "title": "공식 일본어 제목", "page_url": URL,
    }])
    db.save_work(detail("RJ123456"))
    library = Library(tmp_path / "data")
    game = Game("id", "Any [RJ123456]", tmp_path)
    assert db.save_verified_game_link(game.id, "dlsite", "RJ123456")
    def prohibit_network(*a, **kw):
        raise AssertionError("Official names must come from collected DB")
    monkeypatch.setattr(title_workers, "lookup_localized_title", prohibit_network)
    worker = BulkTitleWorker(
        [(game.id, library.title(game), "RJ123456", "dlsite")],
        "ko", library.store / "localized_product_titles.json", db_only=True,
    )
    rows = []
    worker.complete.connect(rows.append)
    worker.run()
    assert rows[0][0]["title"] == "공식 한국어 제목"
    assert rows[0][0]["source"].startswith("PlayDock 공식 작품 DB")
    assert rows[0][0]["language"] == "ko"


def test_first_archive_filename_restores_display_name_without_file_rename(tmp_path):
    library = Library(tmp_path / "data")
    archive = tmp_path / "First Archive [RJ123456].7z"
    archive.write_bytes(b"PRESERVE")
    game = Game("first", "Later Display [RJ123456]", tmp_path, archive=archive)
    library.update_meta(game, original_archive_name=archive.name)
    save_display_title(library, game, "Manually Renamed", source="test")
    assert library.base_title(game) == "Manually Renamed"
    assert restore_filename_title(library, game)
    assert library.base_title(game) == "First Archive [RJ123456]"
    assert archive.read_bytes() == b"PRESERVE"
    assert archive.is_file()
    assert library.meta(game)["original_archive_name"] == archive.name


def test_new_main_screen_names_and_db_only_title_option():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "src/playdock/ui/launcher_layout.py").read_text("utf-8")
    meta = (root / "src/playdock/controllers/metadata.py").read_text("utf-8")
    title = (root / "src/playdock/ui/dialogs/title.py").read_text("utf-8")
    assert '"게임 정보 수집"' in ui
    assert '"배너·아이콘 설정"' in ui
    assert '"게임 이름 설정"' in ui
    assert ui.index('"게임 정보 수집"') < ui.index('"배너·아이콘 설정"')
    assert ui.index('"배너·아이콘 설정"') < ui.index('"게임 이름 설정"')
    assert "scan_button.setEnabled(False)" in ui
    assert "self.has_collected_game_info(game)" in meta or \
           "self.collected_game_record(game)" in meta
    assert "공식 게임명 적용 (수집한 DB)" in title
    assert "db_only=True" in title
    assert "인터넷 이미지 검색·편집" not in ui
