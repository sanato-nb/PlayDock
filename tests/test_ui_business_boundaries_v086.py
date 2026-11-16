"""UI에는 입력·표시·호출만 두는 업무 책임 분리 회귀 검사."""
import ast
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from core import Game, Library
from game_identity import GameIdentity
from game_collections import CollectionStore
from online_artwork import Candidate
from services.artwork_service import ArtworkActions
from services.bulk_title_service import BulkTitleActions, valid_korean_candidate
from services.collection_service import CollectionMembershipActions
from collection_board_model import unassigned_games


ROOT = Path(__file__).resolve().parents[1] / "src" / "playdock"


def sample(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    archive = tmp_path / "Demo Game.zip"
    archive.write_bytes(b"untouched archive bytes")
    library = Library(store=tmp_path / "store")
    game = Game("demo-game", "Demo Game", installed, archive=archive)
    return library, game, archive


def png_bytes():
    output = BytesIO()
    Image.new("RGB", (512, 512), (20, 100, 160)).save(output, format="PNG")
    return output.getvalue()


def test_artwork_code_and_verified_identity_are_saved_without_touching_games(tmp_path):
    library, game, archive = sample(tmp_path)
    actions = ArtworkActions(library, game)
    identity = actions.initial_identity()
    assert not identity.verified
    assert library.meta(game) == {}
    with pytest.raises(ValueError):
        actions.save_product_code("not-a-code", "Demo Game", identity)
    assert library.meta(game) == {}

    code, identity = actions.save_product_code("rj01081508", "Demo Game", identity)
    assert code == "RJ01081508" and not identity.verified
    assert library.meta(game)["product_code"] == code
    assert actions.confirmed_search_code(identity, "Demo Game", code) is None
    assert not actions.record_verified_identity(identity)

    verified = GameIdentity("공식 작품명", "공개 작품정보", code, 1.0, True)
    assert actions.record_verified_identity(verified)
    assert actions.initial_identity().verified
    assert actions.confirmed_search_code(verified, "공식 작품명", code) == code
    assert actions.confirmed_search_code(verified, "다른 작품", code) is None
    assert archive.read_bytes() == b"untouched archive bytes"


def test_artwork_apply_backups_previous_image_and_preserves_metadata(tmp_path):
    library, game, archive = sample(tmp_path)
    library.update_meta(game, title="사용자 제목", launch_exe="game.exe", custom=True)
    actions = ArtworkActions(library, game)
    existing = library.art_dir(game) / "icon.png"
    existing.write_bytes(b"older image")
    candidate = Candidate(
        "Demo Game image", "https://images.example/image.png", "",
        "https://source.example/works/demo", "검색", 512, 512, "출처 확인 필요",
    )
    actions.apply_selection(png_bytes(), candidate, "icon", 50, 50, 100)
    with Image.open(existing) as image:
        assert image.size == (256, 256)
    copies = list((library.store / "backups" / "artwork" / game.id).glob("icon_*.png"))
    assert len(copies) == 1 and copies[0].read_bytes() == b"older image"
    meta = library.meta(game)
    assert meta["title"] == "사용자 제목"
    assert meta["launch_exe"] == "game.exe"
    assert meta["custom"] is True
    assert meta["artwork_sources"]["icon"]["url"] == candidate.image_url
    assert meta["artwork_sources"]["icon"]["page"] == candidate.source_url
    assert meta["artwork_sources"]["icon"]["license"] == "출처 확인 필요"
    assert archive.read_bytes() == b"untouched archive bytes"


def test_artwork_does_not_modify_meta_on_invalid_image(tmp_path):
    library, game, _ = sample(tmp_path)
    actions = ArtworkActions(library, game)
    candidate = Candidate("Demo", "https://example.org/image.png", "", "", "web")
    with pytest.raises(ValueError):
        actions.apply_selection(b"<html>bad</html>", candidate, "hero", 50, 50, 100)
    assert not actions.has_artwork("hero")
    assert library.meta(game) == {}


def test_title_preview_has_no_write_then_preserves_archive_and_history(tmp_path):
    library, game, archive = sample(tmp_path)
    actions = BulkTitleActions(library)
    assert actions.eligible_games([game], skip_custom=True) == [game]
    preview = actions.preview_changes([game], "replace", find="Demo", replacement="새 게임")
    assert len(preview) == 1
    assert preview[0].proposed_name == "새 게임 Game"
    assert library.meta(game) == {}
    changes = actions.prepare_changes([(preview[0], "최종 제목")], "ko")
    assert changes[0].proposed_name == "최종 제목"
    count, backup = actions.apply_changes([game], changes)
    assert count == 1 and backup.is_file()
    assert library.base_title(game) == "최종 제목"
    assert archive.read_bytes() == b"untouched archive bytes"
    assert actions.eligible_games([game], skip_custom=True) == []
    undo = actions.preview_changes([game], "undo")
    assert len(undo) == 1 and undo[0].method == "undo"


def test_title_lookup_keeps_original_language_until_manual_edit(tmp_path):
    library, game, _ = sample(tmp_path)
    actions = BulkTitleActions(library)
    rows = [{"game_id": game.id, "title": "日本語作品", "language": "ja",
             "source": "공개 출처", "code": "RJ01081508"}]
    preview = actions.lookup_preview([game], rows, "ko", save_as_localized=True)
    assert len(preview) == 1 and preview[0].language == "ja"
    unchanged = actions.prepare_changes([(preview[0], "日本語作品")], "ko")[0]
    assert unchanged.language == "ja" and unchanged.source == "공개 출처"
    edited = actions.prepare_changes([(preview[0], "한국어 작품")], "ko")[0]
    assert edited.language == "ko"
    assert "검증 필요" in edited.source
    assert valid_korean_candidate("한국어 작품")
    assert not valid_korean_candidate("English only")


def test_collection_membership_edit_calls_store_without_moving_archive(tmp_path):
    library, game, archive = sample(tmp_path)
    store = CollectionStore(library.store)
    actions = CollectionMembershipActions(store)
    assert actions.choices_for_game(game.id) == []
    cid, name = actions.create("  즐겨찾기  ")
    assert name == "즐겨찾기"
    assert actions.choices_for_game(game.id) == [(cid, "즐겨찾기", False)]
    actions.save_memberships(game.id, {cid})
    assert actions.choices_for_game(game.id) == [(cid, "즐겨찾기", True)]
    assert archive.read_bytes() == b"untouched archive bytes"


def test_unassigned_games_is_a_model_operation_not_a_widget():
    from types import SimpleNamespace
    games = [SimpleNamespace(id="a"), SimpleNamespace(id="b"), SimpleNamespace(id="c")]
    rows = [{"id": "collection", "name": "x", "game_ids": ["a", "missing"]}]
    assert [g.id for g in unassigned_games(games, rows)] == ["b", "c"]


def test_business_writes_do_not_live_in_ui_files():
    ui = ROOT / "ui"
    for path in ui.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        ast.parse(text)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("controllers."), path

    artwork = (ui / "artwork_dialog.py").read_text(encoding="utf-8")
    titles = (ui / "dialogs" / "title.py").read_text(encoding="utf-8")
    library_dialog = (ui / "dialogs" / "library.py").read_text(encoding="utf-8")
    assert "self.artwork_actions.apply_selection(" in artwork
    assert "self.artwork_actions.save_product_code(" in artwork
    for forbidden in ("shutil.copy2(", "save_selected_art(", "self.library.update_meta(",
                      "self.library.set_product_code("):
        assert forbidden not in artwork
    assert "self.bulk_actions.apply_changes(" in titles
    assert "apply_bulk_changes(" not in titles
    assert "BulkChange(" not in titles
    assert "self.memberships.save_memberships(" in library_dialog
    assert "self.collections.set_game_memberships(" not in library_dialog
    assert "self.collections.create(" not in library_dialog
