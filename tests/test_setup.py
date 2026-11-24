from io import BytesIO
from pathlib import Path
import sys
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.setup_paths import normalize_paths, save_folder_settings
from core import Library
import artwork


def test_first_run_wizard_saves_both_paths_and_preserves_existing_values(tmp_path):
    archive = tmp_path / "not_existing_archive_folder"
    game = tmp_path / "not_existing_game_folder"
    settings = tmp_path / "settings.json"
    settings.write_text('{"auto_art":true,"other_setting":42}', encoding="utf-8")
    a, g = save_folder_settings(str(archive), str(game), store_path=settings)
    assert (a, g) == (archive, game)
    assert archive.is_dir() and game.is_dir()
    from core import load_json
    config = load_json(settings)
    assert config["first_run_complete"] is True
    assert config["archives"] == str(archive)
    assert config["library"] == str(game)
    assert config["other_setting"] == 42
    assert config["auto_art"] is False


def test_same_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        normalize_paths(str(tmp_path / "game"), str(tmp_path / "game"))


def test_drive_root_rejected(tmp_path):
    with pytest.raises(ValueError):
        normalize_paths(str(tmp_path.anchor), str(tmp_path / "game"))


def test_existing_file_not_used_as_directory(tmp_path):
    file = tmp_path / "somefile"
    file.write_text("hello")
    with pytest.raises(ValueError):
        normalize_paths(str(file), str(tmp_path / "game"))


def test_no_steam_api_key_supported():
    with pytest.raises(ValueError):
        artwork.get_secret("steamgrid")


def test_manual_images_cached_without_ai_or_steam_api(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    lib = Library(tmp_path / "data")
    from core import Game
    game = Game("sample", "Some Game", root)
    img = Image.new("RGB", (192, 128), (60, 120, 200))
    buf = BytesIO()
    img.save(buf, format="PNG")
    monkeypatch.setattr(artwork, "request_json", lambda *a, **kw: pytest.fail("No AI requests"))
    for kind, size in (("hero", (1600, 520)), ("icon", (256, 256))):
        target = lib.art_dir(game) / f"{kind}.png"
        artwork.save_image(BytesIO(buf.getvalue()), target, kind)
        with Image.open(target) as image:
            assert image.size == size
    assert "artwork_source" not in lib.meta(game)
