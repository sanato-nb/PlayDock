"""Regression: code-only identity -> official website images -> opt-in banner/icon.

No live internet, real user files, image generation or archive extraction.
"""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog

from core import Game, Library
from database.work_repository import WorkDatabase
from experiments.dlsite_detector.code_only import Work, Result
from services.official_artwork_service import (
    OfficialImage, official_image_urls, prepare_official_images,
    trusted_image_url, apply_checked_images, _steam_api_art,
)
from services.identity_artwork_worker import IdentityArtworkThread
from ui.dialogs.identity_artwork import IdentityArtworkDialog
from controllers.metadata import MetadataControllerMixin


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def dl_work():
    return Work("RJ123456", "확인된 게임", "maniax",
                "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                "verified", "dlsite")


@pytest.fixture
def steam_work():
    return Work("1091500", "Steam 작품", "game",
                "https://store.steampowered.com/app/1091500/",
                "verified", "steam")


def png_bytes(size=(1024, 720), color="navy"):
    image = Image.new("RGB", size, color)
    file = BytesIO()
    image.save(file, "PNG")
    return file.getvalue()


def offered(work, kind, color="navy"):
    url = ("https://img.dlsite.jp/modpub/images2/work/RJ123456.jpg"
           if work.store == "dlsite" else
           f"https://cdn.akamai.steamstatic.com/steam/apps/{work.code}/header.jpg")
    return OfficialImage(kind, url, png_bytes(color=color),
                         png_bytes((320, 104) if kind == "hero" else (128, 128), color),
                         work.url)


def test_trust_images_only_from_verified_official_hosts(dl_work, steam_work):
    assert trusted_image_url("dlsite", dl_work.code,
                             "https://img.dlsite.jp/example.jpg")
    assert trusted_image_url("steam", steam_work.code,
                             "https://cdn.akamai.steamstatic.com/steam/apps/1091500/header.jpg")
    assert not trusted_image_url("steam", steam_work.code,
                                 "https://cdn.akamai.steamstatic.com/steam/apps/1091501/header.jpg")
    assert not trusted_image_url("steam", steam_work.code,
                                 "https://evil.example/steam/apps/1091500/header.jpg")
    assert not trusted_image_url("steam", steam_work.code,
                                 "http://cdn.akamai.steamstatic.com/steam/apps/1091500/header.jpg")
    assert not trusted_image_url("dlsite", dl_work.code,
                                 "https://evil.example/RJ123456/cover.jpg")


def test_dlsite_images_selected_only_when_same_verified_code(dl_work):
    cover = "https://img.dlsite.jp/cover.jpg"
    sample = "https://img.dlsite.jp/sample.jpg"
    def fake(code):
        assert code == "RJ123456"
        return {"code": code, "images": [
            {"kind": "cover", "position": 0, "url": cover},
            {"kind": "sample", "position": 0, "url": sample},
        ]}
    candidates = official_image_urls(dl_work, dlsite_fetch=fake)
    assert candidates == {"hero": sample, "icon": cover}
    assert official_image_urls(dl_work, dlsite_fetch=lambda code: {
        "code": "RJ654321", "images": [{"kind": "cover", "url": cover}]}) == {}
    unchecked = Work(dl_work.code, dl_work.title, dl_work.category,
                     dl_work.url, "unavailable", dl_work.store)
    assert official_image_urls(unchecked, dlsite_fetch=fake) == {}


def test_steam_public_appdetails_image_metadata_rejects_cross_app(steam_work):
    good_url = "https://cdn.akamai.steamstatic.com/steam/apps/1091500/header.jpg"
    bad_url = "https://evil.example/steam/apps/1091500/capsule.jpg"
    payload = {"1091500": {"success": True, "data": {
        "steam_appid": 1091500, "header_image": good_url,
        "capsule_image": bad_url,
    }}}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, n): return json.dumps(payload).encode()
    assert _steam_api_art("1091500", opener=lambda *a, **kw: Response()) == {
        "hero": good_url, "icon": good_url,
    }
    payload["1091500"]["data"]["steam_appid"] = 9999999
    assert _steam_api_art("1091500", opener=lambda *a, **kw: Response()) == {}


def test_official_image_download_isolated_per_checkbox(dl_work):
    url = "https://img.dlsite.jp/cover.jpg"
    calls = []
    def fail_first(url):
        calls.append(url)
        if len(calls) == 1:
            raise ValueError("CDN blocked")
        return png_bytes()
    offers = prepare_official_images(
        dl_work, candidates={"hero": url, "icon": url},
        downloader=fail_first, preview_builder=lambda *a, **kw: png_bytes(),
    )
    assert "hero" not in offers
    assert "icon" in offers


def test_ui_has_two_unchecked_independent_checkboxes(app, dl_work):
    offers = {"hero": offered(dl_work, "hero"), "icon": offered(dl_work, "icon")}
    dialog = IdentityArtworkDialog(dl_work, offers, existing_kinds={"hero"})
    try:
        assert not dialog.apply_banner.isChecked()
        assert not dialog.apply_icon.isChecked()
        assert dialog.selected_kinds() == set()
        dialog.apply_icon.setChecked(True)
        assert dialog.selected_kinds() == {"icon"}
        dialog.apply_banner.setChecked(True)
        assert dialog.selected_kinds() == {"hero", "icon"}
        dialog.apply_icon.setChecked(False)
        assert dialog.selected_kinds() == {"hero"}
    finally:
        dialog.close()
    missing = IdentityArtworkDialog(dl_work, {})
    try:
        assert not missing.apply_banner.isEnabled()
        assert not missing.apply_icon.isEnabled()
        assert missing.selected_kinds() == set()
    finally:
        missing.close()


def test_checkbox_only_icon_keeps_existing_banner_identical(tmp_path, dl_work):
    library = Library(tmp_path / "data")
    game = Game("id1", "Test [RJ123456]", tmp_path)
    cache = library.art_dir(game)
    old_banner = png_bytes((1600, 520), "purple")
    old_icon = png_bytes((256, 256), "red")
    (cache / "hero.png").write_bytes(old_banner)
    (cache / "icon.png").write_bytes(old_icon)
    offers = {"hero": offered(dl_work, "hero", "yellow"),
              "icon": offered(dl_work, "icon", "blue")}
    assert apply_checked_images(library, game, dl_work, offers, set()) == []
    assert (cache / "hero.png").read_bytes() == old_banner
    assert (cache / "icon.png").read_bytes() == old_icon
    assert apply_checked_images(library, game, dl_work, offers, {"icon"}) == ["icon"]
    assert (cache / "hero.png").read_bytes() == old_banner
    assert (cache / "icon.png").read_bytes() != old_icon
    backups = list((library.store / "backups" / "artwork" / game.id).glob("icon_*.png"))
    assert len(backups) == 1 and backups[0].read_bytes() == old_icon
    assert not list((library.store / "backups" / "artwork" / game.id).glob("hero_*.png"))


def test_only_banner_selected_does_not_modify_manual_icon(tmp_path, dl_work):
    library = Library(tmp_path / "data")
    game = Game("id2", "Test [RJ123456]", tmp_path)
    cache = library.art_dir(game)
    icon = png_bytes((256, 256), "green")
    (cache / "icon.png").write_bytes(icon)
    offers = {"hero": offered(dl_work, "hero")}
    assert apply_checked_images(library, game, dl_work, offers, {"hero"}) == ["hero"]
    assert (cache / "icon.png").read_bytes() == icon
    assert (cache / "hero.png").is_file()


def test_db_official_artwork_urls_persist_without_extra_tables(tmp_path, dl_work):
    db = WorkDatabase(tmp_path / "data")
    result = Result("RJ123456.zip", "archive", "confirmed",
                    (dl_work,), selected_store="dlsite")
    assert db.save_verified_results([result]) == 1
    assert db.save_official_image_urls("dlsite", "RJ123456", {
        "hero": "https://img.dlsite.jp/cover.jpg",
        "icon": "https://img.dlsite.jp/thumb.jpg",
    }) == 2
    record = db.get_work("RJ123456")
    assert {i["kind"] for i in record["images"]} == {"hero", "icon"}
    assert db.save_official_image_urls("dlsite", "RJ123456", {
        "hero": "https://evil.example/cover.jpg",
    }) == 0
    assert len(db.get_work("RJ123456")["images"]) == 2
    with db.connect() as con:
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert names == {"works", "library_links"}


def test_background_worker_uses_standalone_scanner_engine(monkeypatch, dl_work):
    from services import identity_artwork_worker as module
    result = Result("RJ123456.zip", "archive", "confirmed",
                    (dl_work,), selected_store="dlsite")
    seen = []
    def fake_check(item):
        seen.append((item.label, item.origin))
        return result
    monkeypatch.setattr(module, "check", fake_check)
    monkeypatch.setattr(module, "prepare_official_images", lambda work:
                        {"hero": offered(work, "hero")})
    worker = IdentityArtworkThread("RJ123456.zip")
    responses = []
    worker.complete.connect(lambda result, work, artwork:
                            responses.append((result, work, artwork)))
    worker.run()  # Direct call: deterministic test without a real network thread.
    assert seen == [("RJ123456.zip", "archive")]
    assert len(responses) == 1
    assert responses[0][1].code == dl_work.code
    assert "hero" in responses[0][2]


def test_identity_controller_accept_with_both_unchecked_saves_db_only(
        tmp_path, dl_work, monkeypatch):
    from controllers import metadata as module
    library = Library(tmp_path / "data")
    game = Game("test", "Example [RJ123456]", tmp_path)
    cache = library.art_dir(game)
    (cache / "hero.png").write_bytes(b"ORIGINAL-BANNER")
    (cache / "icon.png").write_bytes(b"ORIGINAL-ICON")
    db = WorkDatabase(library.store)
    result = Result("Example [RJ123456].zip", "archive", "confirmed",
                    (dl_work,), selected_store="dlsite")
    class FakeDialog:
        def __init__(self, *a, **kw): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def selected_kinds(self): return set()
    monkeypatch.setattr(module, "IdentityArtworkDialog", FakeDialog)
    class Stub(MetadataControllerMixin):
        def __init__(self):
            self.library = library
            self.work_db = db
            self.games = [game]
            self.messages = []
        def reload(self, prefer_id=None): pass
        def set_message(self, msg): self.messages.append(msg)
    stub = Stub()
    stub._show_identity_artwork_result(game.id, result, dl_work, {
        "hero": offered(dl_work, "hero"),
        "icon": offered(dl_work, "icon"),
    })
    assert db.get_work("RJ123456")["title"] == "확인된 게임"
    assert (cache / "hero.png").read_bytes() == b"ORIGINAL-BANNER"
    assert (cache / "icon.png").read_bytes() == b"ORIGINAL-ICON"
    assert library.meta(game)["artwork_identity_code"] == "RJ123456"
    assert library.meta(game)["artwork_identity_store"] == "dlsite"


def test_official_artwork_action_is_in_top_function_menu():
    repo = Path(__file__).resolve().parents[1]
    actions = (repo / "src/playdock/controllers/window_actions.py").read_text("utf-8")
    assert "공식 배너·아이콘 적용..." in actions
    assert "self.has_official_image_candidates(game)" in actions
    assert "self.identify_selected_game" in actions


def test_confirmed_steam_fallback_wins_over_failed_dlsite_from_filename(tmp_path):
    from services.official_work_service import explicit_work_identity
    library = Library(tmp_path / "data")
    game = Game("mixed", "Wrong [RJ123456] [Steam 1091500]", tmp_path)
    library.update_meta(
        game, artwork_identity_store="steam", artwork_identity_code="1091500")
    assert explicit_work_identity(library, game) == ("steam", "1091500")
    # Explicit manual user choice still wins over scanner evidence.
    library.update_meta(game, product_code="RJ123456")
    assert explicit_work_identity(library, game) == ("dlsite", "RJ123456")


def test_existing_manual_image_requires_extra_confirmation_before_replace(
        tmp_path, dl_work, monkeypatch):
    from controllers import metadata as module
    library = Library(tmp_path / "data")
    game = Game("manual", "Game [RJ123456]", tmp_path)
    folder = library.art_dir(game)
    old_hero = b"ORIGINAL-USER-MANUAL-HERO"
    (folder / "hero.png").write_bytes(old_hero)
    db = WorkDatabase(library.store)
    result = Result("Game [RJ123456].zip", "archive", "confirmed",
                    (dl_work,), selected_store="dlsite")
    class CheckedDialog:
        def __init__(self, *a, **kw): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def selected_kinds(self): return {"hero"}
    monkeypatch.setattr(module, "IdentityArtworkDialog", CheckedDialog)
    calls = []
    def refuse(*args, **kwargs):
        calls.append((args, kwargs))
        return False
    monkeypatch.setattr(module, "ask_yes_no", refuse)
    class Stub(MetadataControllerMixin):
        def __init__(self):
            self.library, self.work_db, self.games = library, db, [game]
        def reload(self, prefer_id=None): pass
        def set_message(self, msg): pass
    Stub()._show_identity_artwork_result(game.id, result, dl_work,
                                        {"hero": offered(dl_work, "hero")})
    assert len(calls) == 1
    assert (folder / "hero.png").read_bytes() == old_hero
    assert db.get_work("RJ123456")["title"] == "확인된 게임"
    assert not (library.store / "backups" / "artwork").exists()
