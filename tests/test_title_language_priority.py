"""All verified locales are retained; priority is a display rule, not a filter."""
from core import Game, Library
from database.work_repository import WorkDatabase
from services.bulk_title_service import BulkTitleActions
from services.simple_title_edit import undo_display_title
from workers.title import BulkTitleWorker, _prioritized_titles_from_record


def test_priority_collects_every_valid_locale_and_skips_mislabeled_titles():
    record = {"title":"日本語タイトル", "titles":{"ko":"日本語タイトル",
              "ja":"日本語タイトル", "en":"English Title"}}
    selected, source, lang, variants, sources = _prioritized_titles_from_record(
        record, ("ko","ja","en"), store="dlsite")
    assert lang == "ja" and selected == "日本語タイトル"
    assert variants == {"ja":"日本語タイトル","en":"English Title"}
    assert _prioritized_titles_from_record(record, ("en","ko","ja"), store="dlsite")[2] == "en"


def test_priority_batch_keeps_all_titles_and_applies_fallback_for_named_game(tmp_path):
    lib = Library(tmp_path / "data")
    archive = tmp_path / "Local name [RJ123456] [v1].zip"
    archive.write_bytes(b"original")
    game = Game("game", archive.stem, tmp_path, archive=archive)
    db = WorkDatabase(lib.store)
    db.save_work({"code":"RJ123456","fallback_title":"日本語タイトル",
                  "titles":{"ja":"日本語タイトル","en":"English Title"},
                  "page_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"})
    assert db.save_verified_game_link(game.id,"dlsite","RJ123456")
    worker = BulkTitleWorker([(game.id,lib.title(game),"RJ123456","dlsite")], "ko",
                            lib.store / "localized_product_titles.json", db_only=True,
                            priority=("ko","ja","en"))
    results = []
    worker.complete.connect(results.append)
    worker.run()
    actions = BulkTitleActions(lib)
    record = actions.lookup_preview([game],results[0],"ko",save_as_localized=True)[0]
    status, checked = actions.preview_status(game,record,record.proposed_name,"ko")
    assert checked and "2개 언어" in status
    final = actions.preview_display(game,record,record.proposed_name,"ko")
    changes = actions.prepare_changes([(record,record.proposed_name)],"ko")
    count, backup = actions.apply_changes([game],changes)
    assert count == 1 and backup.is_file()
    assert lib.title(game) == final and final.startswith("日本語タイトル")
    assert lib.meta(game)["localized_titles"] == {"ja":"日本語タイトル","en":"English Title"}
    assert lib.meta(game)["title_language_priority"] == ["ko","ja","en"]
    assert archive.read_bytes() == b"original"
    assert undo_display_title(lib,game)
    assert lib.title(game) == archive.stem
    assert not lib.meta(game).get("title_language_priority")


def test_priority_with_english_first_and_steam_base_korean():
    record = {"title":"한국어 게임", "titles":{"en":"English Game"}}
    assert _prioritized_titles_from_record(record, ("ko","ja","en"), store="steam")[2] == "ko"
    assert _prioritized_titles_from_record(record, ("en","ja","ko"), store="steam")[2] == "en"
