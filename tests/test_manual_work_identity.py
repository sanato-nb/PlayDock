import pytest
from core import Game, Library
from database.work_repository import WorkDatabase
from services.manual_work_identity import save_manual_work_identity, current_work_choice
from services.catalog_collection_service import game_catalog_entries, entry_input, partition_catalog_entries, make_missing_code_prompt
from services.official_work_service import official_metadata_for_game
from integrations.official_lookup.code_only import codes_in, steam_ids_in


def test_manual_identity_override_delete_and_verified_link(tmp_path):
    lib = Library(tmp_path / "data")
    archive = tmp_path / "Example [RJ123456] [Steam 123456].zip"
    archive.write_bytes(b"original")
    game = Game("game", archive.stem, tmp_path, archive=archive)
    db = WorkDatabase(lib.store)
    db._upsert_verified([{"store":"dlsite", "code":"RJ123456", "title":"Old",
                          "page_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"},
                         {"store":"steam", "code":"654321", "title":"New",
                          "page_url":"https://store.steampowered.com/app/654321/"}])
    assert db.save_verified_game_link(game.id, "dlsite", "RJ123456")
    lib.update_meta(game, title="My title", prefer_manual_title=True, launch_exe="game.exe")
    assert save_manual_work_identity(lib, game, db, "steam", "654321")
    assert db.get_link(game.id) is None
    db.sync_library(lib, [game])
    assert db.get_link(game.id) is None
    assert official_metadata_for_game(lib, game, db) is None
    assert current_work_choice(lib, game, db) == ("steam", "654321")
    entry = game_catalog_entries(lib, [game])[0]
    assert not codes_in(entry_input(entry).label)
    assert steam_ids_in(entry_input(entry).label) == ("654321",)
    assert db.save_verified_game_link(game.id, "steam", "654321")
    db.sync_library(lib, [game])
    assert official_metadata_for_game(lib, game, db)["title"] == "New"
    assert save_manual_work_identity(lib, game, db, "dlsite", "rj999999")
    entry = game_catalog_entries(lib, [game])[0]
    assert codes_in(entry_input(entry).label) == ("RJ999999",)
    assert not steam_ids_in(entry_input(entry).label)
    assert save_manual_work_identity(lib, game, db, "none", "")
    db.sync_library(lib, [game])
    eligible, missing = partition_catalog_entries(game_catalog_entries(lib, [game]))
    assert not eligible and len(missing) == 1
    assert not make_missing_code_prompt(missing)
    assert db.get_link(game.id) is None
    assert lib.base_title(game) == "My title"
    assert lib.meta(game)["launch_exe"] == "game.exe"
    assert archive.read_bytes() == b"original"
    assert db.count_works() == 2


@pytest.mark.parametrize("store,code", [("steam","0"), ("dlsite","123456"), ("unknown","RJ123456")])
def test_invalid_manual_code_does_not_write(tmp_path, store, code):
    lib = Library(tmp_path / "data")
    game = Game("game", "Example", tmp_path)
    db = WorkDatabase(lib.store)
    before = lib.meta(game)
    with pytest.raises(ValueError):
        save_manual_work_identity(lib, game, db, store, code)
    assert lib.meta(game) == before


def test_work_code_dialog_validates_and_cancels_without_writes(monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog
    from ui.dialogs.work_code import WorkCodeDialog
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt = QApplication.instance() or QApplication([])
    dialog = WorkCodeDialog("Example", "dlsite", "RJ123456", True)
    try:
        assert dialog.selection() == ("dlsite", "RJ123456")
        dialog.store.setCurrentIndex(dialog.store.findData("steam"))
        assert not dialog.apply.isEnabled()
        dialog.code.setText("654321")
        assert dialog.apply.isEnabled()
        assert dialog.selection() == ("steam", "654321")
        dialog.store.setCurrentIndex(dialog.store.findData("none"))
        assert dialog.selection() == ("", "")
        dialog.reject()
        assert dialog.result() == QDialog.DialogCode.Rejected
    finally:
        dialog.close()
