"""Shared title storage and exact rendered preview regressions."""
import pytest
from core import Game, Library
from database.work_repository import WorkDatabase
from services.bulk_title_service import BulkTitleActions
from services.simple_title_edit import (
    save_localized_display_title, save_display_title, undo_display_title,
    original_display_name, restore_filename_title,
)
from workers.title import _title_from_record


def test_steam_localized_titles_use_verified_link_and_keep_files(tmp_path):
    lib = Library(tmp_path / "data")
    archive = tmp_path / "Example [Steam 123456] [v1].zip"
    archive.write_bytes(b"original")
    installed = tmp_path / "installed"
    installed.mkdir()
    game = Game("steam-game", archive.stem, installed, archive=archive)
    db = WorkDatabase(lib.store)
    db._upsert_verified([{"store":"steam", "code":"123456", "title":"Example Game",
                          "page_url":"https://store.steampowered.com/app/123456/"}])
    assert db.save_verified_game_link(game.id, "steam", "123456")
    lib.update_meta(game, localized_titles={"en":"Example Game"}, launch_exe="game.exe")
    actions = BulkTitleActions(lib)
    rows = [{"game_id":game.id, "original":lib.title(game), "store":"steam",
             "code":"123456", "language":"ko", "title":"한국어 게임", "source":"DB"}]
    change = actions.lookup_preview([game], rows, "ko", save_as_localized=True)[0]
    assert change.method == "localized" and change.product_store == "steam"
    expected = actions.preview_display(game, change, change.proposed_name, "ko")
    ready, rejected = actions.partition_changes([game], [change])
    assert ready == [change] and not rejected
    count, backup = actions.apply_changes([game], ready)
    assert count == 1 and backup.is_file()
    assert lib.title(game) == expected
    assert lib.meta(game)["localized_titles"] == {"en":"Example Game", "ko":"한국어 게임"}
    assert lib.meta(game)["launch_exe"] == "game.exe"
    lib.settings["title_language"] = "en"
    assert lib.title(game).startswith("Example Game")
    lib.settings["title_language"] = "ko"
    assert undo_display_title(lib, game)
    assert lib.meta(game)["localized_titles"] == {"en":"Example Game"}
    assert archive.read_bytes() == b"original"
    assert archive.name == "Example [Steam 123456] [v1].zip"
    lib.update_meta(game, product_code="")
    ready, rejected = actions.partition_changes([game], [change])
    assert not ready and rejected


def test_shared_localized_save_is_validated_and_reversible(tmp_path):
    lib = Library(tmp_path / "data")
    game = Game("game", "Example [RJ123456]", tmp_path)
    save_display_title(lib, game, "My custom title")
    with pytest.raises(ValueError, match="언어"):
        save_localized_display_title(lib, game, "日本語タイトル", "ko", "DB")
    assert lib.base_title(game) == "My custom title"
    assert save_localized_display_title(lib, game, "한국어 이름", "ko", "DB")
    assert lib.base_title(game).startswith("한국어 이름")
    assert not save_localized_display_title(lib, game, "한국어 이름", "ko", "DB")
    assert undo_display_title(lib, game)
    assert lib.base_title(game) == "My custom title"


def test_original_name_preview_and_restore_share_safe_rule(tmp_path):
    lib = Library(tmp_path / "data")
    game = Game("game", "Current", tmp_path)
    lib.update_meta(game, original_archive_name="bad/path.zip")
    assert original_display_name(lib, game) == "Current"
    lib.update_meta(game, original_archive_name="First name.ZiP")
    save_display_title(lib, game, "Changed")
    actions = BulkTitleActions(lib)
    change = actions.preview_changes([game], "original")[0]
    assert change.proposed_name == "First name"
    assert actions.preview_display(game, change, change.proposed_name, "ko") == "First name"
    assert restore_filename_title(lib, game)
    assert lib.title(game) == "First name"


def test_db_title_conflicting_locale_is_not_used_as_requested():
    record = {"title":"日本語タイトル", "titles":{"ko":"日本語タイトル", "ja":"日本語タイトル"}}
    title, source, language = _title_from_record(record, "ko", store="dlsite")
    assert title == "日本語タイトル" and language == "ja"
    assert _title_from_record({"title":"日本語タイトル", "titles":{"ko":"日本語タイトル"}},
                              "ko", store="steam") is None
