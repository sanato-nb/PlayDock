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
    assert "파일명 변경 스크립트" in p
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


def test_topbar_placement_separates_official_and_manual_actions():
    root = Path(__file__).resolve().parents[1]
    ui = (root / "src/playdock/ui/launcher_layout.py").read_text("utf-8")
    top, bottom = ui.split("outer.addWidget(top)", 1)
    assert top.index("게임 정보 수집") < top.index("새로고침") < top.index("'기능'") < top.index('"설정"')
    assert "게임 정보 수집" not in bottom
    assert "self.extra_menu_btn = ChevronMenuButton('게임 관리')" in bottom
    assert "이미지 직접 지정" not in bottom


def test_game_management_menu_applies_to_only_the_displayed_game(app, tmp_path, monkeypatch):
    import app as application
    from PIL import Image
    from ui.dialogs.common import PlayDockFileDialog as QFileDialog
    from controllers import game_actions, metadata

    archive_root = tmp_path / "archives"
    root = tmp_path / "installed"
    archive_root.mkdir()
    root.mkdir()
    archive = archive_root / "Example.7z"
    archive.write_bytes(b"archive content must remain untouched")
    other_archive = archive_root / "Other.zip"
    other_archive.write_bytes(b"other archive")
    installed = root / archive.stem
    installed.mkdir()
    exe = installed / "Example.exe"
    exe.write_bytes(b"MZ executable fixture")
    lib = Library(tmp_path / "data")
    lib.settings["archives"] = str(archive_root)
    lib.settings["library"] = str(root)
    monkeypatch.setattr(application, "Library", lambda: lib)

    window = application.MainWindow()
    try:
        games = {game.name: game for game in window.games}
        game = games["Example"]
        other = games["Other"]
        assert game.installed
        menus = []
        monkeypatch.setattr(window.extra_menu_btn, "present_popup",
                            lambda menu, **kwargs: menus.append(menu))

        def open_menu():
            window.extra_menu_btn.click()
            return menus[-1].actions()

        window.populate_games(other.id)
        assert not open_menu()[2].isEnabled()

        window.populate_games(game.id)
        rename, artwork, launch, official = open_menu()
        assert [action.text() for action in (rename, artwork, launch, official)] == [
            "게임 이름 변경 (수동)", "배너·아이콘 수동 설정",
            "실행 옵션 설정", "공식 작품 페이지 열기",
        ]
        assert all(action.isEnabled() for action in (rename, artwork, launch))
        assert not official.isEnabled()  # no official URL yet

        monkeypatch.setattr(metadata, "ask_text", lambda *args: ("새 표시 이름", True))
        rename.trigger()
        assert lib.base_title(game) == "새 표시 이름"
        assert lib.base_title(other) == "Other"
        assert window.current().id == game.id

        image = tmp_path / "custom.png"
        Image.new("RGB", (16, 16), "red").save(image)
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(image), ""))
        for action in artwork.menu().actions():
            action.trigger()
        for kind, size in (("hero", (1600, 520)), ("icon", (256, 256))):
            with Image.open(lib.art_dir(game) / f"{kind}.png") as result:
                assert result.size == size
            assert not (lib.art_dir(other) / f"{kind}.png").exists()

        monkeypatch.setattr(game_actions, "ask_text", lambda *args: ("--windowed", True))
        launch.trigger()
        assert lib.meta(game)["launch_args"] == "--windowed"
        assert "launch_args" not in lib.meta(other)

        messages = []
        opened = []
        monkeypatch.setattr(metadata, "show_message", lambda *args: messages.append(args[1]))
        monkeypatch.setattr(metadata.webbrowser, "open", lambda url: opened.append(url) or True)
        official.trigger()
        assert messages == []  # disabled action never opens a dialog
        assert opened == []

        url = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
        window.work_db._upsert_verified([{
            "store": "dlsite", "code": "RJ123456",
            "title": "검증된 공식 작품", "page_url": url,
        }])
        assert window.work_db.save_verified_game_link(game.id, "dlsite", "RJ123456")
        window.reload(prefer_id=game.id)
        assert open_menu()[3].isEnabled()
        open_menu()[3].trigger()
        assert opened == [url]
        assert "DLsite" in window.game_info.text()
        assert archive.read_bytes() == b"archive content must remain untouched"
        assert other_archive.read_bytes() == b"other archive"
        assert exe.read_bytes() == b"MZ executable fixture"

        window.show_collections_overview()
        assert all(not action.isEnabled() for action in open_menu())
        window.show_all_games()
        window.search.setText("no matching game")
        assert all(not action.isEnabled() for action in open_menu())
    finally:
        window.close()
