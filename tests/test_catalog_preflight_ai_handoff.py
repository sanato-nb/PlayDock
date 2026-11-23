"""User workflow: top-right scan, pre-exclude no-ID archives, AI handoff after scan.

No real network, personal games, or archive modifications.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QWidget

from core import Game, Library
from database.work_repository import WorkDatabase
from controllers.catalog_collection import CatalogCollectionControllerMixin
from services.catalog_collection_service import (
    CatalogEntry, CatalogEvent, partition_catalog_entries,
    make_missing_code_prompt, game_catalog_entries,
)
from ui.dialogs.catalog_collection import CatalogCollectionDialog


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_preflight_only_accepts_identifiers_in_archive_filename(tmp_path):
    library = Library(tmp_path / "data")
    root = tmp_path / "private archives"
    root.mkdir()
    paths = [
        root / "6월의 너와 나 [RJ01081508].7z",
        root / "Steam Example [Steam 1091500].zip",
        root / "Goblin Nest [v1.36].zip",
        root / "Puzzle Game [v1.0].rar",
    ]
    for p in paths:
        p.write_bytes(b"KEEP ALL ORIGINAL ARCHIVE BYTES")
    games = [Game(f"game{i}", p.stem, root, archive=p)
             for i, p in enumerate(paths)]
    # A displayed title, or even a manually stored code, is NOT a code
    # appearing in the archive filename. Keep this one out of web lookups.
    library.update_meta(games[2], title="Goblin [RJ123456]",
                        product_code="RJ123456")
    full = game_catalog_entries(library, games)
    eligible, missing = partition_catalog_entries(full)
    assert [e.label for e in eligible] == [paths[0].name, paths[1].name]
    assert [e.label for e in missing] == [paths[2].name, paths[3].name]
    assert all(p.read_bytes() == b"KEEP ALL ORIGINAL ARCHIVE BYTES" for p in paths)
    assert not list((library.store).rglob("playdock.db"))


def test_ai_handoff_lists_only_no_code_without_private_paths():
    inputs = [
        CatalogEntry("private-1", "Goblin Nest [v1.36].zip"),
        CatalogEntry("private-2", "Game \"Mystery\" [beta].7z"),
    ]
    p = make_missing_code_prompt(inputs)
    assert "Goblin Nest [v1.36].zip" in p
    assert 'Game \\"Mystery\\"' in p  # filename is JSON-escaped
    assert "DLsite" in p and "Steam" in p
    assert "품번" in p and "미확인" in p
    assert "private-1" not in p and "private-2" not in p
    assert "이름 변경 스크립트" in p
    assert "C:\\\\" not in p and "/Users/" not in p
    assert make_missing_code_prompt([]) == ""


def test_prompt_buttons_only_after_successful_completion(app, monkeypatch, tmp_path):
    dialog = CatalogCollectionDialog(
        2, excluded_no_code=("Goblin Nest.zip", "No Steam ID.7z"),
        prompt_text=make_missing_code_prompt(
            [CatalogEntry("a", "Goblin Nest.zip"),
             CatalogEntry("b", "No Steam ID.7z")]),
    )
    try:
        assert not dialog.prompt_copy_button.isEnabled()
        assert not dialog.prompt_save_button.isEnabled()
        assert "Goblin Nest.zip" in dialog.failures.toPlainText()
        assert "사전 제외 2개" in dialog.preflight.text()
        event = CatalogEvent("g", "RJ123456.zip", "fetched", "ok", saved=1)
        dialog.on_progress(1, 2, event)
        assert not dialog.prompt_copy_button.isEnabled()
        dialog.on_complete([event], interrupted=False)
        assert dialog.prompt_copy_button.isEnabled()
        assert dialog.prompt_save_button.isEnabled()
        dialog.copy_missing_prompt()
        assert QApplication.clipboard().text() == dialog.prompt_text
        filename = tmp_path / "AI_Prompt.txt"
        monkeypatch.setattr(
            "ui.dialogs.catalog_collection.QFileDialog.getSaveFileName",
            lambda *args, **kwargs: (str(filename), "텍스트 파일 (*.txt)"),
        )
        dialog.save_missing_prompt()
        assert filename.read_text(encoding="utf-8-sig") == dialog.prompt_text
        assert "TXT 저장 완료" in dialog.prompt_save_button.text()
    finally:
        dialog.close()

    cancelled = CatalogCollectionDialog(
        1, excluded_no_code=("No ID.zip",),
        prompt_text=make_missing_code_prompt([CatalogEntry("m", "No ID.zip")]),
    )
    try:
        cancelled.on_complete([], interrupted=True)
        assert not cancelled.prompt_copy_button.isEnabled()
    finally:
        cancelled.close()

    empty = CatalogCollectionDialog(1)
    try:
        empty.on_complete([], interrupted=False)
        assert not empty.prompt_copy_button.isEnabled()
    finally:
        empty.close()


def test_controller_sends_only_eligible_entries_to_worker(app, tmp_path, monkeypatch):
    import controllers.catalog_collection as module
    directory = tmp_path / "archives"
    directory.mkdir()
    named = directory / "Found [RJ123456].zip"
    missing = directory / "No Code [v1.2].rar"
    named.write_bytes(b"safe")
    missing.write_bytes(b"safe")
    lib = Library(tmp_path / "data")
    games = [Game("found", named.stem, directory, archive=named),
             Game("missing", missing.stem, directory, archive=missing)]
    work_db = WorkDatabase(lib.store)
    instances = []

    class FakeWorker(QThread):
        progress = Signal(int, int, object)
        complete = Signal(object, bool)
        failed = Signal(str)
        def __init__(self, entries, db_path, parent=None):
            super().__init__(parent)
            self.entries = tuple(entries)
            self.db_path = db_path
            instances.append(self)
        def start(self):
            # Don't contact any official website.
            pass

    monkeypatch.setattr(module, "CatalogCollectionThread", FakeWorker)
    monkeypatch.setattr(module, "ask_yes_no", lambda *args, **kwargs: True)

    class Host(QWidget, CatalogCollectionControllerMixin):
        def __init__(self):
            super().__init__()
            self.games = games
            self.library = lib
            self.work_db = work_db
            self.catalog_worker = None
            self.catalog_dialog = None
        def current(self): return games[0]
        def present_game(self): pass

    host = Host()
    try:
        host.collect_library_information()
        assert len(instances) == 1
        assert [e.label for e in instances[0].entries] == [named.name]
        assert "No Code" in host.catalog_dialog.failures.toPlainText()
        assert not host.catalog_dialog.prompt_copy_button.isEnabled()
        host.catalog_dialog.on_complete([], interrupted=False)
        assert host.catalog_dialog.prompt_copy_button.isEnabled()
        assert lib.meta(games[0])["original_archive_name"] == named.name
        assert lib.meta(games[1])["original_archive_name"] == missing.name
        assert missing.read_bytes() == b"safe"
    finally:
        if host.catalog_dialog:
            host.catalog_dialog.close()
        host.catalog_worker = None
        host.close()


def test_topbar_placement_and_missing_gui_button_activation_source():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "src/playdock/ui/launcher_layout.py").read_text("utf-8")
    lib = (root / "src/playdock/controllers/library.py").read_text("utf-8")
    top = ui.split("outer.addWidget(top)", 1)[0]
    bottom = ui.split("    tools = QHBoxLayout()", 1)[1]
    assert top.index('"게임 정보 수집"') < top.index('"새로고침"') < top.index('"설정"')
    assert '"게임 정보 수집"' not in bottom
    assert 'self.identity_scan_btn.setEnabled(confirmed is not None)' in lib
    assert 'self.identity_scan_btn.setEnabled(False)' in lib
    assert 'self.game_name_btn.setEnabled(False)' in lib


def test_actual_main_window_unlocks_artwork_after_collection_and_refresh(
        app, tmp_path, monkeypatch):
    """Reproduce screenshot: DB says verified but artwork button stayed disabled."""
    import app as application
    archive_root = tmp_path / "archives"
    root = tmp_path / "installed"
    archive_root.mkdir()
    root.mkdir()
    archive = archive_root / "Example [RJ123456].7z"
    archive.write_bytes(b"archive content must remain untouched")
    lib = Library(tmp_path / "data")
    lib.settings["archives"] = str(archive_root)
    lib.settings["library"] = str(root)
    monkeypatch.setattr(application, "Library", lambda: lib)

    window = application.MainWindow()
    try:
        assert len(window.games) == 1
        game = window.games[0]
        window.selected_id = game.id
        window.present_game()
        assert not window.identity_scan_btn.isEnabled()
        window.work_db._upsert_verified([{
            "store": "dlsite", "code": "RJ123456",
            "title": "검증된 공식 작품", "page_url":
            "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
        }])
        assert window.work_db.save_verified_game_link(
            game.id, "dlsite", "RJ123456")
        window.present_game()
        assert window.identity_scan_btn.isEnabled()
        assert "공식 작품 확인" in window.game_info.text()
        window.reload(prefer_id=game.id)
        assert window.identity_scan_btn.isEnabled()
        assert window.game_name_btn.isEnabled()
        assert archive.read_bytes() == b"archive content must remain untouched"
    finally:
        window.close()
