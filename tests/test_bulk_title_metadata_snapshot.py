"""One metadata read per game for read-only bulk-title previews."""
from pathlib import Path

import pytest

from core import Game, Library
from services.bulk_title_edit import preview_undo_name, replace_name
from services.bulk_title_service import BulkTitleActions


@pytest.mark.parametrize("mode", ["manual", "replace", "original", "undo"])
def test_bulk_title_preview_reads_metadata_once(tmp_path, monkeypatch, mode):
    library = Library(tmp_path / "data")
    game = Game("example", "Example [RJ123456]", tmp_path / "installed")
    library.update_meta(
        game, title="Current title", prefer_manual_title=True,
        original_archive_name="Original title.zip",
        title_history=[{"title": "Previous title", "prefer_manual_title": True,
                        "title_source": "", "title_product_code": ""}],
    )
    old = library.title(game)
    base = library.base_title(game)
    expected = {
        "manual": base,
        "replace": replace_name(base, "Current", "Updated"),
        "original": Path("Original title.zip").stem,
        "undo": preview_undo_name(library, game),
    }[mode]
    meta_file = library.art_dir(game) / "meta.json"
    before = meta_file.read_bytes()
    original_meta = library.meta
    calls = []

    def counted(item):
        calls.append(item.id)
        return original_meta(item)

    monkeypatch.setattr(library, "meta", counted)
    rows = BulkTitleActions(library).preview_changes(
        [game], mode, find="Current", replacement="Updated")
    assert len(rows) == 1
    assert rows[0].expected_name == old
    assert rows[0].proposed_name == expected
    assert calls == [game.id]
    assert meta_file.read_bytes() == before


def test_title_pair_uses_supplied_empty_snapshot(tmp_path, monkeypatch):
    library = Library(tmp_path / "data")
    game = Game("sample", "Sample", tmp_path)
    library.update_meta(game, title="Stored title", prefer_manual_title=True)
    def unexpected(_game):
        pytest.fail("An explicitly supplied empty metadata snapshot must not be reloaded")
    monkeypatch.setattr(library, "meta", unexpected)
    assert library.title_pair(game, meta={}) == ("Sample", "Sample")
    assert library.base_title(game, meta={}) == "Sample"
